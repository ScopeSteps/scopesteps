from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response, status

from scopesteps.audit.client import audit_recorder
from scopesteps.backlog.client import BacklogVersionId
from scopesteps.identity.client import (
    Permission,
    ProjectAccess,
    ProjectAccessResolver,
    get_project_access,
    get_project_access_resolver,
)
from scopesteps.infrastructure.database import utc_now
from scopesteps.infrastructure.http import IdempotencyKey, SessionDep
from scopesteps.jira_integration.application import connections, publishing
from scopesteps.jira_integration.client import JiraRuntime, publish_context
from scopesteps.jira_integration.domain.connection import JiraConnection
from scopesteps.jira_integration.domain.ids import PublishId
from scopesteps.jira_integration.domain.plan import ISSUE_KINDS, Plan
from scopesteps.jira_integration.domain.publish import OutboxEntry, Publish
from scopesteps.jira_integration.http.schemas import (
    ConnectionResponse,
    ConnectionStatusResponse,
    ConnectRequest,
    FailedItem,
    IssueLinkListResponse,
    IssueLinkResponse,
    KindCounts,
    PreviewResponse,
    PublishListResponse,
    PublishRequest,
    PublishResponse,
    SettingsRequest,
)
from scopesteps.jira_integration.infrastructure.repository import SqlJiraStore
from scopesteps.projects.client import ProjectId

router = APIRouter(tags=["jira_integration"])


def get_jira_runtime(request: Request) -> JiraRuntime:
    runtime: JiraRuntime = request.app.state.jira_runtime
    return runtime


RuntimeDep = Annotated[JiraRuntime, Depends(get_jira_runtime)]
AccessDep = Annotated[ProjectAccess, Depends(get_project_access)]
ResolverDep = Annotated[ProjectAccessResolver, Depends(get_project_access_resolver)]

JIRA_REFUSALS: dict[int | str, dict[str, Any]] = {
    409: {"description": "`JIRA_NOT_CONNECTED`, `VERSION_NOT_APPROVED`, `PUBLISH_IN_PROGRESS`."},
    422: {
        "description": "`JIRA_SITE_INVALID`, `JIRA_AUTH_FAILED`, `JIRA_PROJECT_NOT_FOUND`, "
        "`JIRA_PROJECT_UNSUITABLE`, or a field out of range."
    },
    429: {"description": "`JIRA_RATE_LIMITED`: Jira asked to slow down."},
    502: {"description": "`JIRA_UNAVAILABLE` or `JIRA_REJECTED`."},
    503: {"description": "`JIRA_NOT_CONFIGURED`: the server has no JIRA_TOKEN_KEY."},
}


@router.get("/projects/{project_id}/jira/connection")
def get_connection(
    project_id: ProjectId, access: AccessDep, runtime: RuntimeDep, session: SessionDep
) -> ConnectionStatusResponse:
    """Whether the project is connected to Jira, and what you may do with it. Any member; the
    token is never returned and the account email only to approvers."""
    connection = connections.view_connection(SqlJiraStore(session), access)
    manager = access.can(Permission.DECIDE_VERSIONS)
    return ConnectionStatusResponse(
        configured=runtime.cipher is not None,
        connection=None
        if connection is None
        else _connection_response(connection, show_email=manager),
        can_publish=connection is not None and publishing.can_publish(access, connection),
        can_manage=manager,
    )


@router.put("/projects/{project_id}/jira/connection", responses=JIRA_REFUSALS)
def connect(
    project_id: ProjectId,
    body: ConnectRequest,
    access: AccessDep,
    runtime: RuntimeDep,
    session: SessionDep,
) -> ConnectionResponse:
    """Test the details against Jira Cloud, then save them; the token is stored encrypted and
    never returned. Approver only. Moving to another site or Jira project forgets which issues
    earlier publishes made, so later publishes create new ones there (ADR 0029)."""
    connection = connections.connect(
        SqlJiraStore(session),
        audit_recorder(session),
        runtime.open_gateway,
        runtime.cipher,
        access,
        connections.Connect(
            site_url=body.site_url,
            email=body.email,
            api_token=body.api_token.get_secret_value(),
            project_key=body.project_key,
        ),
        utc_now(),
    )
    session.commit()
    return _connection_response(connection)


@router.post("/projects/{project_id}/jira/connection/test", responses=JIRA_REFUSALS)
def test_connection(
    project_id: ProjectId, access: AccessDep, runtime: RuntimeDep, session: SessionDep
) -> ConnectionResponse:
    """Check the saved details still work in Jira. Approver only."""
    connection = connections.test_connection(
        SqlJiraStore(session), runtime.open_gateway, runtime.cipher, access, utc_now()
    )
    session.commit()
    return _connection_response(connection)


@router.patch("/projects/{project_id}/jira/connection", responses=JIRA_REFUSALS)
def change_settings(
    project_id: ProjectId, body: SettingsRequest, access: AccessDep, session: SessionDep
) -> ConnectionResponse:
    """Turn automatic publishing on or off, and choose who may publish. Approver only; 409
    `CONNECTION_CHANGED` when the revision is stale."""
    connection = connections.change_settings(
        SqlJiraStore(session),
        audit_recorder(session),
        access,
        body.expected_revision,
        utc_now(),
        auto_publish=body.auto_publish,
        publishers=body.publishers,
    )
    session.commit()
    return _connection_response(connection)


@router.delete("/projects/{project_id}/jira/connection", status_code=status.HTTP_204_NO_CONTENT)
def disconnect(project_id: ProjectId, access: AccessDep, session: SessionDep) -> Response:
    """Delete the connection and its token. Issues already in Jira stay there. Approver only."""
    connections.disconnect(SqlJiraStore(session), audit_recorder(session), access, utc_now())
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/projects/{project_id}/jira/preview", responses=JIRA_REFUSALS)
def preview(
    project_id: ProjectId,
    version_id: Annotated[BacklogVersionId, Query()],
    access: AccessDep,
    runtime: RuntimeDep,
    session: SessionDep,
) -> PreviewResponse:
    """How many epics, stories and tasks publishing the approved version would create, update
    and close. Sends nothing to Jira. Approver only; 409 `VERSION_NOT_APPROVED` for a draft or
    a proposed version."""
    context = publish_context(session, runtime)
    plan = publishing.preview(context, access, version_id)
    connection = context.connections.connection(access.project_id)
    return PreviewResponse(
        version_id=version_id,
        jira_project_key="" if connection is None else connection.jira_project.key,
        counts=_plan_counts(plan),
    )


@router.post(
    "/projects/{project_id}/jira/publishes",
    status_code=status.HTTP_201_CREATED,
    responses=JIRA_REFUSALS,
)
def start_publish(
    project_id: ProjectId,
    body: PublishRequest,
    idempotency_key: IdempotencyKey,
    access: AccessDep,
    runtime: RuntimeDep,
    session: SessionDep,
) -> PublishResponse:
    """Plan publishing an approved version and store the plan as an outbox. Nothing is sent
    until the first advance. Approver only. The same key returns the same publish, and so does
    asking again for a version whose publish is still sending (ADR 0029)."""
    context = publish_context(session, runtime)
    publish = publishing.start(context, access, body.version_id, idempotency_key, utc_now())
    session.commit()
    return _publish_response(publish, context.publishes.entries(publish.id))


@router.get("/projects/{project_id}/jira/publishes")
def list_publishes(
    project_id: ProjectId, access: AccessDep, runtime: RuntimeDep, session: SessionDep
) -> PublishListResponse:
    context = publish_context(session, runtime)
    return PublishListResponse(
        publishes=[
            _publish_response(publish, context.publishes.entries(publish.id))
            for publish in publishing.recent(context, access)
        ]
    )


@router.get("/projects/{project_id}/jira/issues")
def list_issue_links(
    project_id: ProjectId, access: AccessDep, runtime: RuntimeDep, session: SessionDep
) -> IssueLinkListResponse:
    """The Jira issue each epic, story and task became, for any member to follow."""
    connection, links = publishing.issue_links(publish_context(session, runtime), access)
    return IssueLinkListResponse(
        issues=[
            IssueLinkResponse(
                item_id=link.item_id,
                kind=link.kind,
                jira_key=link.jira_key,
                url=None if connection is None else connection.issue_url(link.jira_key),
                closed=link.closed,
            )
            for link in links
        ]
    )


@router.get("/jira/publishes/{publish_id}")
def get_publish(
    publish_id: PublishId, resolve: ResolverDep, runtime: RuntimeDep, session: SessionDep
) -> PublishResponse:
    context = publish_context(session, runtime)
    publish = publishing.publish_for(context, publish_id)
    entries = publishing.view(context, resolve(publish.project_id), publish)
    return _publish_response(publish, entries)


@router.post("/jira/publishes/{publish_id}/advance", responses=JIRA_REFUSALS)
def advance_publish(
    publish_id: PublishId, resolve: ResolverDep, runtime: RuntimeDep, session: SessionDep
) -> PublishResponse:
    """Send the publish's next operations to Jira now, up to ten. The server's background sender
    does this on its own (ADR 0029), so the app never has to; this is for sending at once. Safe
    to repeat: while the background sender holds the publish, or Jira asked to wait, it returns
    the publish as it is."""
    context = publish_context(session, runtime)
    publish = publishing.publish_for(context, publish_id)
    advanced = publishing.advance(
        context, resolve(publish.project_id), publish, session.commit, utc_now
    )
    session.commit()
    return _publish_response(advanced, context.publishes.entries(publish_id))


@router.post("/jira/publishes/{publish_id}/retry", responses=JIRA_REFUSALS)
def retry_publish(
    publish_id: PublishId, resolve: ResolverDep, runtime: RuntimeDep, session: SessionDep
) -> PublishResponse:
    """Send a failed publish's failed items again, then advance it. Approver only."""
    context = publish_context(session, runtime)
    publish = publishing.publish_for(context, publish_id)
    retried = publishing.retry(context, resolve(publish.project_id), publish)
    session.commit()
    return _publish_response(retried, context.publishes.entries(publish_id))


def _connection_response(
    connection: JiraConnection, *, show_email: bool = True
) -> ConnectionResponse:
    return ConnectionResponse(
        site_url=connection.site_url,
        email=connection.email if show_email else None,
        jira_project_key=connection.jira_project.key,
        jira_project_name=connection.jira_project.name,
        auto_publish=connection.auto_publish,
        publishers=connection.publishers,
        connected_by=connection.connected_by,
        connected_at=connection.connected_at,
        checked_at=connection.checked_at,
        revision=connection.revision,
    )


def _plan_counts(plan: Plan) -> list[KindCounts]:
    return [
        KindCounts(
            kind=kind,
            create=counts.create,
            update=counts.update,
            close=counts.close,
            unchanged=counts.unchanged,
        )
        for kind, counts in plan.counts().items()
    ]


def _publish_response(publish: Publish, entries: list[OutboxEntry]) -> PublishResponse:
    counts = [
        KindCounts(
            kind=kind,
            create=sum(1 for e in entries if e.kind == kind and e.operation == "create"),
            update=sum(1 for e in entries if e.kind == kind and e.operation == "update"),
            close=sum(1 for e in entries if e.kind == kind and e.operation == "close"),
            unchanged=0,
        )
        for kind in ISSUE_KINDS
    ]
    return PublishResponse(
        id=publish.id,
        version_id=BacklogVersionId(publish.version_id),
        status=publish.status,
        created_by=publish.created_by,
        created_at=publish.created_at,
        finished_at=publish.finished_at,
        last_error=publish.last_error,
        next_attempt_at=publish.next_attempt_at,
        total=len(entries),
        sent=sum(1 for entry in entries if entry.state == "done"),
        counts=counts,
        failed=[
            FailedItem(
                item_id=entry.item_id,
                kind=entry.kind,
                operation=entry.operation,
                error_code=entry.error_code or "",
            )
            for entry in entries
            if entry.state == "failed"
        ],
        revision=publish.revision,
    )
