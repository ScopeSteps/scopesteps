from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from scopesteps.audit.domain.event import AuditActor, AuditEvent, EventType, Subject
from scopesteps.audit.domain.ids import AuditEventId
from scopesteps.kernel.ids import new_id
from scopesteps.projects.client import ProjectId


class EventWriter(Protocol):
    def add(self, event: AuditEvent) -> None:
        """Insert within the caller's transaction; the caller commits. There is no other write."""
        ...


def record_event(
    store: EventWriter,
    *,
    project_id: ProjectId,
    actor: AuditActor,
    type: EventType,  # noqa: A002
    subjects: Sequence[Subject],
    summary: str,
    occurred_at: datetime,
) -> AuditEvent:
    event = AuditEvent(
        id=AuditEventId(new_id()),
        project_id=project_id,
        actor=actor,
        type=type,
        subjects=tuple(subjects),
        summary=summary,
        occurred_at=occurred_at,
    )
    store.add(event)
    return event
