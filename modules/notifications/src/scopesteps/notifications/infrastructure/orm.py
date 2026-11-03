from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from scopesteps.infrastructure.database import Base, UtcDateTime


class NotificationRecord(Base):
    __tablename__ = "notifications_notifications"
    __table_args__ = (
        # Matches the list: one person, newest first, id as the tie-breaker.
        Index("ix_notifications_list", "user_id", "created_at", "id"),
        Index("ix_notifications_comment", "comment_id", "kind"),
        Index("ix_notifications_email_waiting", "email_waiting", "created_at"),
        Index("ix_notifications_created_at", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"))
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects_projects.id"))
    # These name `backlog`'s and `discussions`' records, which come and go on their own terms.
    item_id: Mapped[UUID | None]
    thread_id: Mapped[UUID]
    comment_id: Mapped[UUID]
    kind: Mapped[str] = mapped_column(String(16))
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    read_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    # True until the sender has decided on an email for it, sent or not.
    email_waiting: Mapped[bool]


class EmailSettingsRecord(Base):
    """A person's choices; no row means the defaults."""

    __tablename__ = "notifications_email_settings"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"), primary_key=True)
    email_on_mention: Mapped[bool]
    email_on_reply: Mapped[bool]


class EmailWindowRecord(Base):
    """When a person last got an email about a thread."""

    __tablename__ = "notifications_email_windows"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"), primary_key=True)
    thread_id: Mapped[UUID] = mapped_column(primary_key=True)
    last_sent_at: Mapped[datetime] = mapped_column(UtcDateTime, index=True)
