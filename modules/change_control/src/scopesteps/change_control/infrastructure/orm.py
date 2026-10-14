from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

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
