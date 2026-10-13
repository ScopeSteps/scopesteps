from typing import Annotated

from fastapi import APIRouter, Depends, Query

from scopesteps.audit.application.feed import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, list_activity
from scopesteps.audit.domain.event import AuditEvent
from scopesteps.audit.http.schemas import (
    ActivityActor,
    ActivityEvent,
    ActivityFeedResponse,
    ActivitySubject,
)
from scopesteps.audit.infrastructure.repository import SqlAuditEventRepository
from scopesteps.identity.client import ProjectAccess, get_project_access
from scopesteps.infrastructure.http import SessionDep
from scopesteps.projects.client import ProjectId

router = APIRouter(tags=["audit"])


@router.get("/projects/{project_id}/activity")
def list_project_activity(
    project_id: ProjectId,
    access: Annotated[ProjectAccess, Depends(get_project_access)],
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    cursor: Annotated[
        str | None,
        Query(max_length=200, description="`next_cursor` of the previous page."),
    ] = None,
) -> ActivityFeedResponse:
    """The project's activity log, newest first. Any member may read it; entries never change."""
    page = list_activity(SqlAuditEventRepository(session), access, limit=limit, cursor=cursor)
    return ActivityFeedResponse(
        events=[_event_response(event) for event in page.events], next_cursor=page.next_cursor
    )


def _event_response(event: AuditEvent) -> ActivityEvent:
    return ActivityEvent(
        id=event.id,
        project_id=event.project_id,
        type=event.type,
        actor=ActivityActor(
            kind=event.actor.kind,
            user_id=event.actor.user_id,
            display_name=event.actor.display_name,
        ),
        subjects=[ActivitySubject(kind=subject.kind, id=subject.id) for subject in event.subjects],
        summary=event.summary,
        occurred_at=event.occurred_at,
    )
