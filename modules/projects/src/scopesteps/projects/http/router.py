from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from scopesteps.audit.client import audit_recorder
from scopesteps.backlog.client import load_scope_statuses
from scopesteps.evidence.client import EvidenceRef
from scopesteps.identity.client import (
    Actor,
    Memberships,
    ProjectAccess,
    Role,
    get_actor,
    get_memberships,
    get_project_access,
)
from scopesteps.infrastructure.database import utc_now
from scopesteps.infrastructure.http import IdempotencyKey, SessionDep
from scopesteps.projects.application import people, projects
from scopesteps.projects.application.projects import ProjectView, StatusReader
from scopesteps.projects.client import (
    PersonEvidence,
    PersonId,
    ProjectId,
    ProjectReader,
    ProjectRef,
)
from scopesteps.projects.domain.limits import ProjectLimits
from scopesteps.projects.domain.person import Person
from scopesteps.projects.domain.project import MAX_NAME_CHARS, ConcurrentCommandError
from scopesteps.projects.http.schemas import (
    BacklogLimitsResponse,
    ConfirmedRightsResponse,
    ConversationLimitsResponse,
    CorrectionRequest,
    CorrectionResponse,
    CreateProjectRequest,
    ExtractedPersonResponse,
    PeopleResponse,
    PersonResponse,
    ProjectDetailResponse,
    ProjectLimitsResponse,
    ProjectListResponse,
    ProjectResponse,
    RenameProjectRequest,
    RightsRequest,
    RunLimitsSummary,
    ScopeStatusResponse,
    SourceLimitsResponse,
)
from scopesteps.projects.infrastructure.repository import (
    SqlPeopleRepository,
    SqlProjectRepository,
    SqlReceiptStore,
)
from scopesteps.sources.client import SourceBlockId, SourceVersionId

router = APIRouter(tags=["projects"])

ActorDep = Annotated[Actor, Depends(get_actor)]
MembershipsDep = Annotated[Memberships, Depends(get_memberships)]
ProjectAccessDep = Annotated[ProjectAccess, Depends(get_project_access)]


def get_project_limits(request: Request) -> ProjectLimits:
    limits: ProjectLimits = request.app.state.project_limits
    return limits


ProjectLimitsDep = Annotated[ProjectLimits, Depends(get_project_limits)]


@router.get("/projects")
def list_projects(
    actor: ActorDep, memberships: MembershipsDep, session: SessionDep
) -> ProjectListResponse:
    """The projects the actor is a member of, by name, each with the actor's roles and status."""
    views = projects.list_projects(
        SqlProjectRepository(session), memberships, _status_reader(session), actor
    )
    return ProjectListResponse(projects=[_summary(view) for view in views])


@router.post("/projects", status_code=status.HTTP_201_CREATED)
def create_project(
    body: CreateProjectRequest,
    idempotency_key: IdempotencyKey,
    actor: ActorDep,
    memberships: MembershipsDep,
    limits: ProjectLimitsDep,
    session: SessionDep,
) -> ProjectDetailResponse:
    """Create a project and make the actor its editor and approver.

    Names need not be unique. Repeating the request with the same Idempotency-Key returns the
    project it created.
    """
    view = projects.create_project(
        SqlProjectRepository(session),
        SqlReceiptStore(session),
        memberships,
        _status_reader(session),
        actor,
        projects.CreateProject(idempotency_key=idempotency_key, name=body.name),
        utc_now(),
    )
    _commit(session)
    return _detail(view, limits)


@router.get("/projects/{project_id}")
def get_project(
    project_id: ProjectId, access: ProjectAccessDep, limits: ProjectLimitsDep, session: SessionDep
) -> ProjectDetailResponse:
    """The project with the limits that apply to it."""
    view = projects.get_project(SqlProjectRepository(session), _status_reader(session), access)
    return _detail(view, limits)


@router.patch("/projects/{project_id}")
def rename_project(
    project_id: ProjectId,
    body: RenameProjectRequest,
    idempotency_key: IdempotencyKey,
    access: ProjectAccessDep,
    limits: ProjectLimitsDep,
    session: SessionDep,
) -> ProjectDetailResponse:
    """Rename the project. Needs the editor or approver role.

    409 `PROJECT_CHANGED` means `expected_revision` is stale: read the project again.
    """
    view = projects.rename_project(
        SqlProjectRepository(session),
        SqlReceiptStore(session),
        audit_recorder(session),
        _status_reader(session),
        access,
        projects.RenameProject(
            idempotency_key=idempotency_key,
            name=body.name,
            expected_revision=body.expected_revision,
        ),
        utc_now(),
    )
    _commit(session)
    return _detail(view, limits)


@router.get("/projects/{project_id}/people")
def list_people(
    project_id: ProjectId, access: ProjectAccessDep, session: SessionDep
) -> PeopleResponse:
    """Everyone the project's sources name, oldest first, with the agent's reading, any
    correction and any confirmed decision rights. Any role on the project may read."""
    found = people.list_people(SqlPeopleRepository(session), access)
    return PeopleResponse(people=[_person(person) for person in found])


@router.put("/projects/{project_id}/people/{person_id}/correction")
def correct_person(
    project_id: ProjectId,
    person_id: PersonId,
    body: CorrectionRequest,
    idempotency_key: IdempotencyKey,
    access: ProjectAccessDep,
    session: SessionDep,
) -> PersonResponse:
    """Correct a person's name or role. Needs the editor role. The agent's reading is kept in
    `extracted`.

    409 `PERSON_CHANGED` means `expected_revision` is stale: read the people again.
    """
    person = people.correct_person(
        SqlPeopleRepository(session),
        SqlReceiptStore(session),
        audit_recorder(session),
        access,
        people.CorrectPerson(
            idempotency_key=idempotency_key,
            person_id=person_id,
            expected_revision=body.expected_revision,
            name=body.name,
            role=body.role,
        ),
        utc_now(),
    )
    _commit(session)
    return _person(person)


@router.put("/projects/{project_id}/people/{person_id}/rights")
def confirm_rights(
    project_id: ProjectId,
    person_id: PersonId,
    body: RightsRequest,
    idempotency_key: IdempotencyKey,
    access: ProjectAccessDep,
    session: SessionDep,
) -> PersonResponse:
    """Confirm the decision rights of a person whose rights no source states. Needs the editor
    role.

    409 `RIGHTS_STATED_IN_SOURCE` when a source states them; 409 `PERSON_CHANGED` when
    `expected_revision` is stale.
    """
    person = people.confirm_rights(
        SqlPeopleRepository(session),
        SqlReceiptStore(session),
        audit_recorder(session),
        access,
        people.ConfirmRights(
            idempotency_key=idempotency_key,
            person_id=person_id,
            expected_revision=body.expected_revision,
            rights=body.rights,
        ),
        utc_now(),
    )
    _commit(session)
    return _person(person)


def resolve_project_reader(session: SessionDep) -> ProjectReader:
    """The implementation the composition root binds to `client.get_project_reader`."""
    projects_by_id = SqlProjectRepository(session)

    def read(project_id: ProjectId) -> ProjectRef | None:
        project = projects_by_id.get(project_id)
        return None if project is None else ProjectRef(id=project.id, name=project.name)

    return read


def _status_reader(session: Session) -> StatusReader:
    return lambda project_ids: load_scope_statuses(session, project_ids)


def _commit(session: Session) -> None:
    try:
        session.commit()
    except IntegrityError as error:
        # A concurrent request with the same Idempotency-Key won the unique constraint. Nothing
        # of this request was stored.
        session.rollback()
        raise ConcurrentCommandError(
            "Another request with this Idempotency-Key finished first. Try again."
        ) from error


_ROLE_ORDER: Callable[[Role], int] = list(Role).index


def _summary(view: ProjectView) -> ProjectResponse:
    project, scope = view.project, view.status
    return ProjectResponse(
        id=project.id,
        name=project.name,
        roles=sorted(view.roles, key=_ROLE_ORDER),
        revision=project.revision,
        status=ScopeStatusResponse(
            state=scope.state,
            baseline_version=scope.baseline_version,
            baseline_version_id=scope.baseline_version_id,
            open_version_id=scope.open_version_id,
        ),
        created_at=project.created_at,
    )


def _detail(view: ProjectView, limits: ProjectLimits) -> ProjectDetailResponse:
    return ProjectDetailResponse(
        **_summary(view).model_dump(),
        limits=ProjectLimitsResponse(
            project_name_max_chars=MAX_NAME_CHARS,
            source=SourceLimitsResponse(
                max_bytes=limits.source_max_bytes, max_words=limits.source_max_words
            ),
            run=RunLimitsSummary(
                max_turns=limits.run_max_turns,
                max_tool_calls=limits.run_max_tool_calls,
                max_clarification_rounds=limits.run_max_clarification_rounds,
            ),
            backlog=BacklogLimitsResponse(
                max_epics=limits.backlog_max_epics, max_stories=limits.backlog_max_stories
            ),
            conversation=ConversationLimitsResponse(max_message_chars=limits.message_max_chars),
        ),
    )


def _evidence(evidence: tuple[PersonEvidence, ...]) -> list[EvidenceRef]:
    return [
        EvidenceRef(
            source_version_id=SourceVersionId(e.source_version_id),
            block_id=SourceBlockId(e.block_id),
            quote=e.quote,
        )
        for e in evidence
    ]


def _person(person: Person) -> PersonResponse:
    extracted, correction, confirmed = person.extracted, person.correction, person.confirmed_rights
    return PersonResponse(
        id=person.id,
        project_id=person.project_id,
        revision=person.revision,
        name=person.name,
        role=person.role,
        extracted=ExtractedPersonResponse(
            name=extracted.name,
            role=extracted.role,
            said=extracted.said,
            stated_rights=extracted.stated_rights,
            evidence=_evidence(extracted.evidence),
            rights_evidence=_evidence(extracted.rights_evidence),
            run_id=person.run_id,
            extracted_at=person.extracted_at,
        ),
        correction=None
        if correction is None
        else CorrectionResponse(
            name=correction.name,
            role=correction.role,
            corrected_by=correction.corrected_by,
            corrected_at=correction.corrected_at,
        ),
        confirmed_rights=None
        if confirmed is None
        else ConfirmedRightsResponse(
            rights=confirmed.rights,
            confirmed_by=confirmed.confirmed_by,
            confirmed_at=confirmed.confirmed_at,
        ),
        created_at=person.created_at,
    )
