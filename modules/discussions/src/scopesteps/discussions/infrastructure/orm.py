from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from scopesteps.infrastructure.database import Base, UtcDateTime


class ThreadRecord(Base):
    __tablename__ = "discussions_threads"
    __table_args__ = (
        # Matches the list: one project, newest activity first, id as the tie-breaker.
        Index("ix_discussions_threads_activity", "project_id", "last_activity_at", "id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects_projects.id"))
    # Not a foreign key: item ids are stable across backlog versions and belong to `backlog`.
    item_id: Mapped[UUID | None] = mapped_column(index=True)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    last_activity_at: Mapped[datetime] = mapped_column(UtcDateTime)
    open_comments: Mapped[int]
    # Compare-and-set guard for resolve and reopen; posting a comment leaves it alone.
    revision: Mapped[int]
    resolved_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    resolved_by: Mapped[UUID | None] = mapped_column(ForeignKey("identity_users.id"))
    resolved_by_name: Mapped[str | None] = mapped_column(String(200))


class CommentRecord(Base):
    __tablename__ = "discussions_comments"
    __table_args__ = (
        Index("ix_discussions_comments_thread", "thread_id", "created_at", "id"),
        Index("ix_discussions_comments_rate", "project_id", "author_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    thread_id: Mapped[UUID] = mapped_column(ForeignKey("discussions_threads.id"))
    # Copied for the rate limit, so counting a member's recent comments needs no join.
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects_projects.id"))
    author_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"))
    author_name: Mapped[str] = mapped_column(String(200))
    # What a member wrote, mentions as <@user_id>: shown to members, never logged or audited, and
    # sent to the agent only as a person quotes it into a change request.
    body: Mapped[str] = mapped_column(Text)
    # Not a foreign key, like `item_id`: it only says which version the comment was written by.
    backlog_version_id: Mapped[UUID | None]
    revision: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    edited_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    deleted_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class CommandReceiptRecord(Base):
    __tablename__ = "discussions_command_receipts"
    __table_args__ = (UniqueConstraint("actor_id", "idempotency_key"),)

    id: Mapped[UUID] = mapped_column(primary_key=True)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    fingerprint: Mapped[str] = mapped_column(String(64))
    thread_id: Mapped[UUID] = mapped_column(ForeignKey("discussions_threads.id"))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)


class ThreadFollowerRecord(Base):
    """A person following a thread, or, with `muted`, one who unfollowed it and stays out."""

    __tablename__ = "discussions_thread_followers"

    thread_id: Mapped[UUID] = mapped_column(ForeignKey("discussions_threads.id"), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("identity_users.id"), primary_key=True, index=True
    )
    muted: Mapped[bool]


class ChangeRequestLinkRecord(Base):
    """A change request a person made from a thread. A thread can be sent more than once; a
    request comes from one thread at most."""

    __tablename__ = "discussions_change_requests"

    change_request_id: Mapped[UUID] = mapped_column(
        # Named here because the generated name is over Postgres's 63 characters.
        ForeignKey("change_control_change_requests.id", name="fk_discussions_change_requests_id"),
        primary_key=True,
    )
    thread_id: Mapped[UUID] = mapped_column(ForeignKey("discussions_threads.id"), index=True)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
