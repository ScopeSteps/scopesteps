from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from scopesteps.backlog.client import load_scope_statuses
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
from scopesteps.projects.application import projects
from scopesteps.projects.application.projects import ProjectView, StatusReader
from scopesteps.projects.client import ProjectId, ProjectReader, ProjectRef
from scopesteps.projects.domain.limits import ProjectLimits
from scopesteps.projects.domain.project import MAX_NAME_CHARS, ConcurrentCommandError
from scopesteps.projects.http.schemas import (
    BacklogLimitsResponse,
    CreateProjectRequest,
    ProjectDetailResponse,
    ProjectLimitsResponse,
    ProjectListResponse,
    ProjectResponse,
    RenameProjectRequest,
    RunLimitsSummary,
    ScopeStatusResponse,
    SourceLimitsResponse,
)
from scopesteps.projects.infrastructure.repository import SqlProjectRepository, SqlReceiptStore

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
        ),
    )
