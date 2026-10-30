from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sqlalchemy.orm import Session

from scopesteps.audit.application.recording import record_event
from scopesteps.audit.domain.event import (
    MAX_SUBJECTS,
    MAX_SUMMARY_CHARS,
    ActorKind,
    AuditActor,
    EventType,
    Subject,
    SubjectKind,
)
from scopesteps.audit.domain.ids import AuditEventId
from scopesteps.audit.infrastructure.repository import SqlAuditEventRepository
from scopesteps.projects.client import ProjectId


class AuditRecorder(Protocol):
    """The only way a module adds to a project's activity log.

    Call it for an action that really happened (not for an idempotent replay), with the time of
    that action. `summary` is one line built from names, numbers and counts: never source text,
    an answer, a credential or model output. Recorded events are never changed or removed.
    """

    def record(
        self,
        *,
        project_id: ProjectId,
        actor: AuditActor,
        type: EventType,  # noqa: A002
        subjects: Sequence[Subject],
        summary: str,
        occurred_at: datetime,
    ) -> None: ...


class _SessionAuditRecorder:
    def __init__(self, session: Session) -> None:
        self._events = SqlAuditEventRepository(session)

    def record(
        self,
        *,
        project_id: ProjectId,
        actor: AuditActor,
        type: EventType,  # noqa: A002
        subjects: Sequence[Subject],
        summary: str,
        occurred_at: datetime,
    ) -> None:
        record_event(
            self._events,
            project_id=project_id,
            actor=actor,
            type=type,
            subjects=subjects,
            summary=summary,
            occurred_at=occurred_at,
        )


def audit_recorder(session: Session) -> AuditRecorder:
    """A recorder that writes in `session`'s transaction: the event is committed or rolled back
    with the action it describes. It never commits or flushes on its own."""
    return _SessionAuditRecorder(session)


@dataclass(frozen=True)
class RecentActivity:
    events: int
    latest_at: datetime


def recent_activity(
    session: Session, project_ids: Collection[ProjectId], since: datetime
) -> dict[ProjectId, RecentActivity]:
    """How much happened in each project given since `since`, in one query; projects where
    nothing did are absent. Performs no access check: every member may read a project's log."""
    return {
        project_id: RecentActivity(events, latest_at)
        for project_id, (events, latest_at) in SqlAuditEventRepository(session)
        .recent_by_project(project_ids, since)
        .items()
    }


__all__ = [
    "MAX_SUBJECTS",
    "MAX_SUMMARY_CHARS",
    "ActorKind",
    "AuditActor",
    "AuditEventId",
    "AuditRecorder",
    "EventType",
    "RecentActivity",
    "Subject",
    "SubjectKind",
    "audit_recorder",
    "recent_activity",
]
