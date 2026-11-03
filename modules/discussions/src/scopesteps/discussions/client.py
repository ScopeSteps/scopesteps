"""What other modules may use of discussions: their ids, and the link between a thread and the
change request a person made from it. Nothing here hands comment text to anyone: the text reaches
a change request only through what a person submits (ADR 0020)."""

from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from scopesteps.audit.client import audit_recorder
from scopesteps.discussions.application import threads
from scopesteps.discussions.domain.ids import CommentId, ThreadId
from scopesteps.discussions.infrastructure.repository import (
    BacklogItems,
    SqlChangeRequestLinks,
    SqlThreadStore,
)
from scopesteps.identity.client import ProjectAccess
from scopesteps.projects.client import ProjectId


@dataclass(frozen=True)
class ThreadOrigin:
    thread_id: ThreadId
    item_title: str | None
    """The epic or story; None for General discussion."""


def require_thread(session: Session, project_id: ProjectId, thread_id: ThreadId) -> None:
    """Raises NotFoundError unless the thread is in `project_id` and still has a comment. Performs
    no access check."""
    threads.require_thread(SqlThreadStore(session), project_id, thread_id)


def link_change_request(
    session: Session,
    access: ProjectAccess,
    *,
    thread_id: ThreadId,
    change_request_id: UUID,
    change_request_number: int,
    now: datetime,
) -> None:
    """Record, in the caller's transaction, that the actor sent the thread as this change request,
    with its audit event. The caller has checked the actor's role."""
    threads.link_change_request(
        SqlThreadStore(session),
        SqlChangeRequestLinks(session),
        BacklogItems(session),
        audit_recorder(session),
        access,
        thread_id=thread_id,
        change_request_id=change_request_id,
        change_request_number=change_request_number,
        now=now,
    )


def thread_origins(session: Session, request_ids: Collection[UUID]) -> dict[UUID, ThreadOrigin]:
    """Which thread each change request among `request_ids` came from; others are absent. Performs
    no access check."""
    store, items = SqlThreadStore(session), BacklogItems(session)
    origins: dict[UUID, ThreadOrigin] = {}
    for request_id, thread_id in SqlChangeRequestLinks(session).of_requests(request_ids).items():
        thread = store.get(thread_id)
        if thread is None:
            continue
        item = (
            None
            if thread.item_id is None
            else items.describe(thread.project_id, [thread.item_id]).get(thread.item_id)
        )
        origins[request_id] = ThreadOrigin(thread_id, None if item is None else item.title)
    return origins


__all__ = [
    "CommentId",
    "ThreadId",
    "ThreadOrigin",
    "link_change_request",
    "require_thread",
    "thread_origins",
]
