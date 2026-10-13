from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from scopesteps.infrastructure.database import Base, UtcDateTime


class ProjectRecord(Base):
    __tablename__ = "projects_projects"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    revision: Mapped[int] = mapped_column(server_default="1")
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)


class CommandReceiptRecord(Base):
    __tablename__ = "projects_command_receipts"
    __table_args__ = (UniqueConstraint("actor_id", "idempotency_key"),)

    id: Mapped[UUID] = mapped_column(primary_key=True)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects_projects.id"))
    fingerprint: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
