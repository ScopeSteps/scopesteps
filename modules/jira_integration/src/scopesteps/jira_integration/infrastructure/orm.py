from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, ForeignKey, Index, LargeBinary, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from scopesteps.infrastructure.database import Base, UtcDateTime


class ConnectionRecord(Base):
    """A project's Jira connection. The API token is stored encrypted, never in plain text."""

    __tablename__ = "jira_integration_connections"

    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects_projects.id"), primary_key=True)
    site_url: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(254))
    token_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    jira_project_id: Mapped[str] = mapped_column(String(32))
    jira_project_key: Mapped[str] = mapped_column(String(16))
    jira_project_name: Mapped[str] = mapped_column(String(255))
    epic_type_id: Mapped[str] = mapped_column(String(32))
    story_type_id: Mapped[str] = mapped_column(String(32))
    subtask_type_id: Mapped[str] = mapped_column(String(32))
    auto_publish: Mapped[bool]
    revision: Mapped[int]
    connected_by: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"))
    connected_at: Mapped[datetime] = mapped_column(UtcDateTime)
    checked_at: Mapped[datetime] = mapped_column(UtcDateTime)


class PublishRecord(Base):
    __tablename__ = "jira_integration_publishes"
    __table_args__ = (
        UniqueConstraint("project_id", "idempotency_key"),
        Index("ix_jira_integration_publishes_list", "project_id", "created_at", "id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects_projects.id"))
    # `backlog`'s version; approved versions are never deleted.
    version_id: Mapped[UUID]
    idempotency_key: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), index=True)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"))
    created_by_name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    last_error: Mapped[str | None] = mapped_column(String(64))
    revision: Mapped[int]


class OutboxEntryRecord(Base):
    """One operation of a publish, in the order it is sent (ADR 0029)."""

    __tablename__ = "jira_integration_outbox"
    __table_args__ = (UniqueConstraint("publish_id", "position"),)

    id: Mapped[UUID] = mapped_column(primary_key=True)
    publish_id: Mapped[UUID] = mapped_column(ForeignKey("jira_integration_publishes.id"))
    position: Mapped[int]
    item_id: Mapped[UUID]
    kind: Mapped[str] = mapped_column(String(8))
    operation: Mapped[str] = mapped_column(String(8))
    content: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    jira_key: Mapped[str | None] = mapped_column(String(32))
    state: Mapped[str] = mapped_column(String(8))
    error_code: Mapped[str | None] = mapped_column(String(64))
    attempts: Mapped[int]


class IssueLinkRecord(Base):
    """Which Jira issue a ScopeSteps epic, story or task became."""

    __tablename__ = "jira_integration_issue_links"

    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects_projects.id"), primary_key=True)
    item_id: Mapped[UUID] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(8))
    jira_key: Mapped[str] = mapped_column(String(32))
    jira_id: Mapped[str] = mapped_column(String(32))
    fingerprint: Mapped[str] = mapped_column(String(64))
    closed: Mapped[bool]
