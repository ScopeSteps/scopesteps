from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Enum, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from scopesteps.backlog.domain.version import MAX_TITLE_CHARS, VersionState
from scopesteps.infrastructure.database import Base, UtcDateTime


def _state_values(states: type[VersionState]) -> list[str]:
    return [state.value for state in states]


class VersionRecord(Base):
    __tablename__ = "backlog_versions"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects_projects.id"), index=True)
    base_version_id: Mapped[UUID | None] = mapped_column(ForeignKey("backlog_versions.id"))
    revision: Mapped[int]
    state: Mapped[VersionState] = mapped_column(
        Enum(
            VersionState,
            native_enum=False,
            length=16,
            values_callable=_state_values,
        )
    )
    content_hash: Mapped[str] = mapped_column(String(64))
    # Names the layout of the JSON columns here and on the version's items.
    schema_version: Mapped[str] = mapped_column(String(32))
    # Unique so a retried or duplicated step cannot commit a second candidate for one run. Not a
    # foreign key: runs belong to the agent module.
    run_id: Mapped[UUID | None] = mapped_column(unique=True)
    source_version_ids: Mapped[list[str]] = mapped_column(JSON)
    decisions: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    out_of_scope: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    set_aside: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, server_default=text("'[]'")
    )
    created_by: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)


class ItemRevisionRecord(Base):
    """An item as it stands in one version. `item_id` is the id that is stable across versions."""

    __tablename__ = "backlog_item_revisions"
    __table_args__ = (UniqueConstraint("version_id", "item_id"),)

    id: Mapped[UUID] = mapped_column(primary_key=True)
    version_id: Mapped[UUID] = mapped_column(ForeignKey("backlog_versions.id"), index=True)
    item_id: Mapped[UUID]
    position: Mapped[int]
    kind: Mapped[str] = mapped_column(String(16))
    parent_item_id: Mapped[UUID | None]
    title: Mapped[str] = mapped_column(String(MAX_TITLE_CHARS))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class CommandReceiptRecord(Base):
    """An accepted edit, kept so a retry with the same Idempotency-Key does not apply it twice."""

    __tablename__ = "backlog_command_receipts"
    __table_args__ = (UniqueConstraint("actor_id", "idempotency_key"),)

    id: Mapped[UUID] = mapped_column(primary_key=True)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    version_id: Mapped[UUID] = mapped_column(ForeignKey("backlog_versions.id"))
    fingerprint: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
