from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Enum, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from scopesteps.change_control.domain.change_request import ChangeRequestStatus
from scopesteps.infrastructure.database import Base, UtcDateTime


class ApprovalRecord(Base):
    """An approval or rejection of one draft revision. Rows are only ever inserted.

    The current baseline is the approval with the highest `baseline_number` in its project. The
    unique numbers are the compare-and-set that keeps two approvals from replacing the same
    baseline (ADR 0008); rejections have no number, and NULLs never collide.
    """

    __tablename__ = "change_control_approvals"
    __table_args__ = (UniqueConstraint("project_id", "baseline_number"),)

    id: Mapped[UUID] = mapped_column(primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects_projects.id"), index=True)
    # Unique: a version is decided at most once.
    version_id: Mapped[UUID] = mapped_column(ForeignKey("backlog_versions.id"), unique=True)
    decision: Mapped[str] = mapped_column(String(16))
    revision: Mapped[int]
    content_hash: Mapped[str] = mapped_column(String(64))
    baseline_number: Mapped[int | None]
    # Named explicitly: the conventional name is longer than Postgres allows (63 characters).
    previous_baseline_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("backlog_versions.id", name="fk_change_control_approvals_previous_baseline")
    )
    reason: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"))
    decided_at: Mapped[datetime] = mapped_column(UtcDateTime)


class CommandReceiptRecord(Base):
    __tablename__ = "change_control_command_receipts"
    __table_args__ = (UniqueConstraint("actor_id", "idempotency_key"),)

    id: Mapped[UUID] = mapped_column(primary_key=True)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    approval_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "change_control_approvals.id", name="fk_change_control_command_receipts_approval"
        )
    )
    fingerprint: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)


def _status_values(statuses: type[ChangeRequestStatus]) -> list[str]:
    return [status.value for status in statuses]


class ChangeRequestRecord(Base):
    """A change request and where it stands. Its text is also stored as a source version, which
    is what the change cites; this copy is what the list shows."""

    __tablename__ = "change_control_change_requests"
    __table_args__ = (
        # Two requests that read the same highest number cannot both commit.
        UniqueConstraint("project_id", "number"),
        Index("ix_change_control_change_requests_order", "project_id", "requested_at", "id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects_projects.id"))
    number: Mapped[int]
    # What a person asked for; never logged or traced.
    text: Mapped[str] = mapped_column(Text)
    requested_by: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"))
    requested_by_name: Mapped[str] = mapped_column(String(200))
    requested_at: Mapped[datetime] = mapped_column(UtcDateTime)
    base_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("backlog_versions.id", name="fk_change_control_change_requests_base")
    )
    base_content_hash: Mapped[str] = mapped_column(String(64))
    source_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("sources_versions.id", name="fk_change_control_change_requests_source")
    )
    # Unique: a change run analyses one request. Not a foreign key: runs belong to the agent.
    run_id: Mapped[UUID] = mapped_column(unique=True)
    status: Mapped[ChangeRequestStatus] = mapped_column(
        Enum(
            ChangeRequestStatus,
            native_enum=False,
            length=32,
            values_callable=_status_values,
        )
    )
    # Compare-and-set guard: every write checks the revision it read, then increments it.
    revision: Mapped[int]
    candidate_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("backlog_versions.id", name="fk_change_control_change_requests_candidate"),
        unique=True,
    )
    change_set_id: Mapped[UUID | None]
    added_count: Mapped[int | None]
    changed_count: Mapped[int | None]
    removed_count: Mapped[int | None]
    # The agent's analysis in its own words, and its notes per item; shown, never logged.
    analysis: Mapped[str | None] = mapped_column(Text)
    change_set: Mapped[dict[str, Any]] = mapped_column(JSON)
    failure: Mapped[str | None] = mapped_column(String(64))
    analyzed_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
