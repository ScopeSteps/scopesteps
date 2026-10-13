from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, CheckConstraint, Connection, Enum, ForeignKey, Index, String, event
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from scopesteps.audit.domain.event import (
    MAX_ACTOR_NAME_CHARS,
    MAX_SUMMARY_CHARS,
    ActorKind,
    EventType,
)
from scopesteps.infrastructure.database import Base, UtcDateTime


def _enum_values(enum_class: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_class]


class AuditEventRecord(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint(
            "(actor_kind = 'user' AND actor_user_id IS NOT NULL)"
            " OR (actor_kind <> 'user' AND actor_user_id IS NULL)",
            name="actor_matches_kind",
        ),
        # Matches the feed: one project, newest first, id as the tie-breaker.
        Index("ix_audit_events_project_feed", "project_id", "occurred_at", "id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects_projects.id"))
    actor_kind: Mapped[ActorKind] = mapped_column(
        Enum(ActorKind, native_enum=False, length=16, values_callable=_enum_values)
    )
    actor_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("identity_users.id"))
    actor_name: Mapped[str | None] = mapped_column(String(MAX_ACTOR_NAME_CHARS))
    # A plain string column, so a new event type needs no migration.
    type: Mapped[EventType] = mapped_column(
        Enum(EventType, native_enum=False, length=48, values_callable=_enum_values)
    )
    subjects: Mapped[list[dict[str, str]]] = mapped_column(JSON)
    summary: Mapped[str] = mapped_column(String(MAX_SUMMARY_CHARS))
    occurred_at: Mapped[datetime] = mapped_column(UtcDateTime)


class AuditEventImmutableError(RuntimeError):
    """Code tried to change or delete a stored audit event."""


@event.listens_for(AuditEventRecord, "before_update")
@event.listens_for(AuditEventRecord, "before_delete")
def _refuse_change(_mapper: Mapper[Any], _connection: Connection, target: AuditEventRecord) -> None:
    raise AuditEventImmutableError(f"Audit event {target.id} is append-only")
