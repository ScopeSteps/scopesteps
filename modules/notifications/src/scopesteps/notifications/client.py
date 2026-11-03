"""What other modules may use of notifications: telling people that a comment needs them, and
withdrawing that when the comment goes (ADR 0021). Who gets told is the caller's decision."""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from scopesteps.identity.client import UserDirectory
from scopesteps.kernel.email import EmailSender
from scopesteps.notifications.application import emails, notifications
from scopesteps.notifications.application.notifications import NewNotification, Readers
from scopesteps.notifications.domain.ids import NotificationId
from scopesteps.notifications.domain.notification import NotificationKind
from scopesteps.notifications.infrastructure.repository import (
    BacklogItems,
    SqlEmailQueue,
    SqlNotificationStore,
    SqlSettingsStore,
)
from scopesteps.projects.client import ProjectReader


class Notifier(Protocol):
    """Writes join the caller's transaction, so a rolled-back comment tells nobody."""

    def notify(self, new: Sequence[NewNotification]) -> None: ...

    def withdraw(self, comment_id: UUID) -> None:
        """Nobody hears any more about a deleted comment, and no email goes out for it."""
        ...


class _SessionNotifier:
    def __init__(self, session: Session) -> None:
        self._store = SqlNotificationStore(session)

    def notify(self, new: Sequence[NewNotification]) -> None:
        notifications.record_notifications(self._store, new)

    def withdraw(self, comment_id: UUID) -> None:
        self._store.delete_of_comment(comment_id)


def notifier(session: Session) -> Notifier:
    return _SessionNotifier(session)


def send_due_emails(
    session: Session,
    directory: UserDirectory,
    projects: ProjectReader,
    sender: EmailSender,
    base_url: str,
    now: datetime,
) -> int:
    """Send what is due, committing as it goes. For the composition root's background job; the
    session must not be shared with a request."""
    context = emails.EmailContext(
        readers=Readers(directory, projects, BacklogItems(session)),
        settings=SqlSettingsStore(session),
        sender=sender,
        base_url=base_url,
    )
    return emails.send_due_emails(SqlEmailQueue(session), context, now)


def delete_expired_notifications(session: Session, now: datetime) -> int:
    """Past their retention, in the caller's transaction."""
    return notifications.delete_expired(SqlNotificationStore(session), now)


__all__ = [
    "NewNotification",
    "NotificationId",
    "NotificationKind",
    "Notifier",
    "delete_expired_notifications",
    "notifier",
    "send_due_emails",
]
