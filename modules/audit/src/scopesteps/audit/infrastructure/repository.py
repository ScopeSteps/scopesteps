from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from scopesteps.audit.domain.event import (
    ActorKind,
    AuditActor,
    AuditEvent,
    FeedCursor,
    Subject,
    SubjectKind,
)
from scopesteps.audit.domain.ids import AuditEventId
from scopesteps.audit.infrastructure.orm import AuditEventRecord
from scopesteps.identity.client import UserId
from scopesteps.projects.client import ProjectId


class SqlAuditEventRepository:
    """Inserts and reads only. Events are append-only, so there is no update or delete."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, event: AuditEvent) -> None:
        self._session.add(
            AuditEventRecord(
                id=event.id,
                project_id=event.project_id,
                actor_kind=event.actor.kind,
                actor_user_id=event.actor.user_id,
                actor_name=event.actor.display_name,
                type=event.type,
                subjects=[
                    {"kind": subject.kind.value, "id": str(subject.id)}
                    for subject in event.subjects
                ],
                summary=event.summary,
                occurred_at=event.occurred_at,
            )
        )

    def newest_first(
        self, project_id: ProjectId, *, after: FeedCursor | None, limit: int
    ) -> list[AuditEvent]:
        query = select(AuditEventRecord).where(AuditEventRecord.project_id == project_id)
        if after is not None:
            # Spelled out instead of a row-value comparison so SQLite and Postgres agree.
            query = query.where(
                or_(
                    AuditEventRecord.occurred_at < after.occurred_at,
                    and_(
                        AuditEventRecord.occurred_at == after.occurred_at,
                        AuditEventRecord.id < after.id,
                    ),
                )
            )
        records = self._session.scalars(
            query.order_by(AuditEventRecord.occurred_at.desc(), AuditEventRecord.id.desc()).limit(
                limit
            )
        )
        return [_to_event(record) for record in records]


def _to_event(record: AuditEventRecord) -> AuditEvent:
    return AuditEvent(
        id=AuditEventId(record.id),
        project_id=ProjectId(record.project_id),
        actor=AuditActor(
            kind=ActorKind(record.actor_kind),
            user_id=None if record.actor_user_id is None else UserId(record.actor_user_id),
            display_name=record.actor_name,
        ),
        type=record.type,
        subjects=tuple(
            Subject(SubjectKind(subject["kind"]), UUID(subject["id"]))
            for subject in record.subjects
        ),
        summary=record.summary,
        occurred_at=record.occurred_at,
    )
