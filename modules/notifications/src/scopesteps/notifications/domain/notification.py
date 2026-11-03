"""A notification: someone wrote something a person should look at (ADR 0021).

It names who, which project, thread and comment, never what was written. Comments and threads are
named by plain UUIDs: `discussions` builds on this module, so its ids are not available here.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

from scopesteps.identity.client import UserId
from scopesteps.notifications.domain.ids import NotificationId
from scopesteps.projects.client import ProjectId

RETENTION = timedelta(days=90)
EMAIL_WINDOW = timedelta(minutes=15)
"""A person gets at most one email per thread in this time."""

NotificationKind = Literal["mentioned", "replied"]


@dataclass(frozen=True)
class Notification:
    id: NotificationId
    user_id: UserId
    project_id: ProjectId
    item_id: UUID | None
    """The epic or story the thread is on; None for General discussion."""
    thread_id: UUID
    comment_id: UUID
    kind: NotificationKind
    actor_id: UserId
    created_at: datetime
    read_at: datetime | None = None


@dataclass(frozen=True)
class EmailSettings:
    """A person with no saved choice has these defaults."""

    email_on_mention: bool = True
    email_on_reply: bool = False

    def wants(self, notification: Notification) -> bool:
        if notification.kind == "mentioned":
            return self.email_on_mention
        return self.email_on_reply


def worth_emailing(
    waiting: list[Notification], settings: EmailSettings, member_of: frozenset[ProjectId]
) -> list[Notification]:
    """What is still news when the email goes out: a choice changed, a notification read or a
    project left since it was written all drop it."""
    return [
        notification
        for notification in waiting
        if notification.read_at is None
        and notification.project_id in member_of
        and settings.wants(notification)
    ]
