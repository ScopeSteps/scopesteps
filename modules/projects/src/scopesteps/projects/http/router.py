from collections.abc import Callable, Sequence
from typing import Annotated
from uuid import UUID

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
from scopesteps.projects.application import people, projects, speakers
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
from scopesteps.projects.domain.speakers import SpeakerLabel, TranscriptSpeakers
from scopesteps.projects.http.schemas import (
    BacklogLimitsResponse,
    ConfirmedRightsResponse,
    ConversationLimitsResponse,
    CorrectionRequest,
    CorrectionResponse,
    CreateProjectRequest,
    ExtractedPersonResponse,
    LinkSpeakerAnswer,
    MeetingRoleResponse,
    NewParticipantAnswer,
    NotAPersonAnswer,
    PeopleResponse,
    PersonResponse,
    ProjectDetailResponse,
    ProjectLimitsResponse,
    ProjectListResponse,
    ProjectResponse,
    ProjectSpeakersResponse,
    RenameProjectRequest,
    RightsRequest,
    RunLimitsSummary,
    ScopeStatusResponse,
    SourceLimitsResponse,
    SpeakerMappingRequest,
    SpeakerResponse,
    SpokeInResponse,
    TranscriptSpeakersResponse,
    UnconfirmedSpeakerResponse,
)
from scopesteps.projects.infrastructure.repository import (
    SqlPeopleRepository,
    SqlProjectRepository,
    SqlReceiptStore,
    SqlSpeakerMappingRepository,
)
from scopesteps.sources.client import SourceBlockId, SourceVersionId, load_current_speakers

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
    """Everyone on the project, oldest first: people the sources name and participants editors
    confirmed as speakers, with the agent's reading, any correction, meeting role and confirmed
    decision rights, plus the speakers nobody has confirmed yet. Any role may read."""
    found = people.list_people(SqlPeopleRepository(session), access)
    views = speakers.project_speakers(
        SqlPeopleRepository(session),
        SqlSpeakerMappingRepository(session),
        _label_reader(session),
        access.project_id,
    )
    return PeopleResponse(
        people=[_person(person, views) for person in found],
        unconfirmed_speakers=[
            UnconfirmedSpeakerResponse(
                source_id=view.transcript.source_id,
                key=speaker.label.key,
                label=speaker.label.label,
            )
            for view in views
            for speaker in view.speakers
            if not speaker.confirmed
        ],
    )


@router.get("/projects/{project_id}/speakers")
def list_speakers(
    project_id: ProjectId, access: ProjectAccessDep, session: SessionDep
) -> ProjectSpeakersResponse:
    """Each current transcript's speakers with who they are, as far as anyone has said (ADR
    0012). Any role on the project may read."""
    views = speakers.list_speakers(
        SqlPeopleRepository(session),
        SqlSpeakerMappingRepository(session),
        _label_reader(session),
        access,
    )
    return ProjectSpeakersResponse(transcripts=[_transcript(view) for view in views])


@router.put("/projects/{project_id}/sources/{source_id}/speakers")
def assign_speakers(
    project_id: ProjectId,
    source_id: UUID,
    body: SpeakerMappingRequest,
    idempotency_key: IdempotencyKey,
    access: ProjectAccessDep,
    session: SessionDep,
) -> TranscriptSpeakersResponse:
    """Save who each speaker in the transcript is: link a participant, create one with a name
    and meeting role, or mark the label not a person. Needs the editor role. Never blocks or
    starts a run.

    The body is the whole answer; a label left out goes back to unconfirmed. 409
    `SPEAKERS_CHANGED` with `details.current_revision` when `expected_revision` is stale; 422
    `PARTICIPANT_EXISTS` with `details.person_id` when a new participant's name is taken.
    """
    view = speakers.assign_speakers(
        SqlPeopleRepository(session),
        SqlSpeakerMappingRepository(session),
        _label_reader(session),
        SqlReceiptStore(session),
        audit_recorder(session),
        access,
        speakers.AssignSpeakers(
            idempotency_key=idempotency_key,
            source_id=source_id,
            expected_revision=body.expected_revision,
            choices=tuple((answer.label_key, _choice(answer)) for answer in body.speakers),
        ),
        utc_now(),
    )
    _commit(session)
    return _transcript(view)


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


def _choice(
    answer: LinkSpeakerAnswer | NewParticipantAnswer | NotAPersonAnswer,
) -> speakers.SpeakerChoice:
    match answer:
        case LinkSpeakerAnswer():
            return speakers.LinkParticipant(answer.person_id, answer.meeting_role)
        case NewParticipantAnswer():
            return speakers.NewParticipant(answer.name, answer.meeting_role)
        case _:
            return speakers.NotAPerson()


def _label_reader(session: Session) -> speakers.SpeakerLabelReader:
    """Labels come from `sources`; this module never parses source text (ADR 0012)."""

    def read(project_id: ProjectId) -> list[TranscriptSpeakers]:
        return [
            TranscriptSpeakers(
                source_id=found.source.id,
                source_version_id=found.version.id,
                labels=tuple(
                    SpeakerLabel(
                        key=label.key,
                        label=label.label,
                        turn_count=label.turn_count,
                        first_block_id=label.first_block_id,
                        first_paragraph=label.first_block_ordinal,
                        sample=label.sample,
                    )
                    for label in found.speakers
                ),
            )
            for found in load_current_speakers(session, project_id)
        ]

    return read


def _transcript(view: speakers.TranscriptView) -> TranscriptSpeakersResponse:
    return TranscriptSpeakersResponse(
        source_id=view.transcript.source_id,
        source_version_id=view.transcript.source_version_id,
        revision=view.revision,
        speakers=[
            SpeakerResponse(
                key=speaker.label.key,
                label=speaker.label.label,
                turn_count=speaker.label.turn_count,
                first_block_id=speaker.label.first_block_id,
                first_paragraph=speaker.label.first_paragraph,
                sample=speaker.label.sample,
                status=speaker.status,
                person_id=speaker.person_id,
                assigned_by=speaker.assignment.assigned_by if speaker.assignment else None,
                assigned_at=speaker.assignment.assigned_at if speaker.assignment else None,
            )
            for speaker in view.speakers
        ],
    )


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


def _person(person: Person, views: Sequence[speakers.TranscriptView] = ()) -> PersonResponse:
    extracted, correction, confirmed = person.extracted, person.correction, person.confirmed_rights
    meeting_role = person.meeting_role
    return PersonResponse(
        id=person.id,
        project_id=person.project_id,
        revision=person.revision,
        origin=person.origin,
        name=person.name,
        role=person.role,
        entered_name=person.entered_name,
        meeting_role=None
        if meeting_role is None
        else MeetingRoleResponse(
            value=meeting_role.value, set_by=meeting_role.set_by, set_at=meeting_role.set_at
        ),
        spoke_in=[
            SpokeInResponse(
                source_id=view.transcript.source_id,
                label=speaker.label.label,
                status=speaker.status,
            )
            for view in views
            for speaker in view.speakers
            if speaker.person_id == person.id
            and (speaker.status == "linked" or speaker.status == "linked_automatically")
        ],
        extracted=None
        if extracted is None or person.run_id is None or person.extracted_at is None
        else ExtractedPersonResponse(
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
