"""A notification: something a person should look at (ADR 0021).

A discussion notification names who, which project, thread and comment, never what was written.
A Jira notification names the publish or the project's Jira connection, with counts only: never
item titles, Jira's answers or the token. Other modules' records are named by plain UUIDs:
`discussions` and `jira_integration` build on this module, so their ids are not available here.
"""

from collections.abc import Mapping
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

NotificationKind = Literal[
    "mentioned",
    "replied",
    "jira_published",
    "jira_publish_failed",
    "jira_token_expiring",
    "jira_token_stopped",
]
DISCUSSION_KINDS: frozenset[NotificationKind] = frozenset({"mentioned", "replied"})
JIRA_TOKEN_KINDS: frozenset[NotificationKind] = frozenset(
    {"jira_token_expiring", "jira_token_stopped"}
)


@dataclass(frozen=True)
class Notification:
    id: NotificationId
    user_id: UserId
    project_id: ProjectId
    item_id: UUID | None
    """The epic or story the thread is on; None for General discussion and for Jira."""
    thread_id: UUID | None
    """Set for a discussion notification only."""
    comment_id: UUID | None
    kind: NotificationKind
    actor_id: UserId
    created_at: datetime
    read_at: datetime | None = None
    subject_id: UUID | None = None
    """For a Jira notification: the publish, or a key for one state of the project's token. A
    person hears about each subject once."""
    version_id: UUID | None = None
    """The approved version a publish sent."""
    details: Mapping[str, int] | None = None
    """Counts only: created, updated, closed and failed for a publish, days left for a token."""

    @property
    def topic_id(self) -> UUID:
        """What emails are batched by: the thread, or the Jira subject."""
        topic = self.thread_id if self.thread_id is not None else self.subject_id
        if topic is None:
            raise ValueError("A notification names a thread or a subject")
        return topic


@dataclass(frozen=True)
class EmailSettings:
    """A person with no saved choice has these defaults."""

    email_on_mention: bool = True
    email_on_reply: bool = False
    email_on_jira_failure: bool = True

    def wants(self, notification: Notification) -> bool:
        """A finished publish is in-app only; a token about to stop publishing is always sent,
        since the project's Jira stops for everyone otherwise."""
        match notification.kind:
            case "mentioned":
                return self.email_on_mention
            case "replied":
                return self.email_on_reply
            case "jira_publish_failed":
                return self.email_on_jira_failure
            case "jira_published":
                return False
            case "jira_token_expiring" | "jira_token_stopped":
                return True


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
