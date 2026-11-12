"""Notification emails: batched per person and thread (or Jira subject), sent after the commit
that claimed them.

A batch is claimed by moving the person's window for its topic, so two API processes cannot send
the same email. Jira emails carry counts and a link only: never item titles, Jira's answers or
the token. A send that still fails on its one retry is logged and dropped: the in-app
notification stands (ADR 0021). Messages carry who, the project, the item and a link, never
comment text (the rule of ADR 0019).
"""

import html
import logging
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from scopesteps.identity.client import UserId
from scopesteps.kernel.email import EmailMessage, EmailSender, EmailSendError, email_layout
from scopesteps.notifications.application.notifications import (
    ItemReader,
    Readers,
    SettingsStore,
)
from scopesteps.notifications.domain.ids import NotificationId
from scopesteps.notifications.domain.notification import (
    DISCUSSION_KINDS,
    EMAIL_WINDOW,
    JIRA_TOKEN_KINDS,
    EmailSettings,
    Notification,
    worth_emailing,
)
from scopesteps.projects.client import ProjectId

logger = logging.getLogger(__name__)

SEND_ATTEMPTS = 2
GENERAL_DISCUSSION = "General discussion"


class EmailQueue(Protocol):
    """Writes join the caller's transaction; `commit` ends it."""

    def waiting(self) -> list[Notification]:
        """Notifications with no email decision yet, oldest first, in a bounded batch."""
        ...

    def last_sent(self, user_id: UserId, topic_id: UUID) -> datetime | None: ...

    def claim_window(
        self, user_id: UserId, topic_id: UUID, *, seen: datetime | None, now: datetime
    ) -> bool:
        """Compare-and-set: False, and nothing written, if another process moved it first."""
        ...

    def settle(self, notification_ids: Collection[NotificationId]) -> None:
        """Their email has been decided; `waiting` leaves them out from now on."""
        ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


@dataclass(frozen=True)
class EmailContext:
    readers: Readers
    settings: SettingsStore
    sender: EmailSender
    base_url: str


def send_due_emails(queue: EmailQueue, context: EmailContext, now: datetime) -> int:
    """One email for each person and topic (a thread, or a Jira subject) whose window is open. What arrives inside a window
    waits for its end and goes out as one batch, unless it stopped being news. Returns how many
    emails were sent."""
    batches: dict[tuple[UserId, UUID], list[Notification]] = {}
    for notification in queue.waiting():
        batches.setdefault((notification.user_id, notification.topic_id), []).append(notification)
    settings = context.settings.many({user_id for user_id, _ in batches})
    sent = 0
    for (user_id, topic_id), waiting in batches.items():
        last = queue.last_sent(user_id, topic_id)
        if last is not None and now - last < EMAIL_WINDOW:
            continue
        chosen = worth_emailing(
            waiting,
            settings.get(user_id, EmailSettings()),
            context.readers.directory.project_ids(user_id),
        )
        message = _message(context, user_id, chosen) if chosen else None
        if message is not None and not queue.claim_window(user_id, topic_id, seen=last, now=now):
            queue.rollback()
            continue
        queue.settle([n.id for n in waiting])
        queue.commit()
        if message is not None and _deliver(context.sender, message):
            sent += 1
    return sent


def notification_link(base_url: str, notification: Notification) -> str:
    project = f"{base_url}/projects/{notification.project_id}"
    if notification.kind in JIRA_TOKEN_KINDS:
        return f"{project}/backlog"
    if notification.kind in ("jira_published", "jira_publish_failed"):
        version = "" if notification.version_id is None else f"?version={notification.version_id}"
        return f"{project}/backlog{version}"
    return (
        f"{base_url}/projects/{notification.project_id}/discussion"
        f"?thread={notification.thread_id}&comment={notification.comment_id}"
    )


def notification_email(
    *,
    to: str,
    batch: Sequence[Notification],
    actor: str,
    item: str,
    project: str,
    link: str,
) -> EmailMessage:
    """`actor` wrote the newest of `batch`. Names go through one line: they end up in a header."""
    mentions = sum(1 for n in batch if n.kind == "mentioned")
    replies = len(batch) - mentions
    if mentions == 1 and replies == 0:
        what = f"{_line(actor)} mentioned you on"
    elif mentions == 0 and replies == 1:
        what = f"{_line(actor)} replied on"
    elif mentions == 0:
        what = f"{replies} new replies on"
    else:
        what = f"{mentions + replies} new comments for you on"
    about, where = _line(item), _line(project)
    summary = f"{what} {about} in {where}"
    return EmailMessage(
        to=to,
        subject=summary,
        text=f"{summary}.\n\nOpen the discussion: {link}\n",
        html=email_layout(
            [f"{html.escape(what)} <strong>{html.escape(about)}</strong> in {html.escape(where)}."],
            link,
            "Open the discussion",
        ),
    )


def jira_email(*, to: str, notification: Notification, project: str, link: str) -> EmailMessage:
    """Counts and a link only. The project's name goes through one line: it ends up in a header."""
    details = notification.details or {}
    where = _line(project)
    match notification.kind:
        case "jira_publish_failed":
            failed = details.get("failed", 0)
            items = "item" if failed == 1 else "items"
            summary = f"{failed} {items} did not reach Jira from {where}"
            lines = [
                f"{summary}.",
                f"{details.get('sent', 0)} of {details.get('total', 0)} changes were sent. "
                "Open the backlog to see which failed, then retry; only what is missing is sent.",
            ]
            action = "Open and retry"
        case "jira_token_expiring":
            days = details.get("days_left", 0)
            when = "today" if days <= 0 else "tomorrow" if days == 1 else f"in {days} days"
            summary = f"The Jira API token of {where} expires {when}"
            lines = [
                f"{summary}.",
                "Make a new token in Atlassian and reconnect Jira in Project settings, or "
                "publishing to Jira stops.",
            ]
            action = "Open the project"
        case "jira_token_stopped":
            summary = f"Publishing to Jira has stopped in {where}"
            lines = [
                f"{summary}: Jira no longer accepts the saved API token, or it expired.",
                "Reconnect Jira with a new token in Project settings to start again.",
            ]
            action = "Open the project"
        case _:
            summary = f"Published to Jira from {where}"
            lines = [f"{summary}."]
            action = "Open the backlog"
    return EmailMessage(
        to=to,
        subject=summary,
        text="\n\n".join(lines) + f"\n\n{action}: {link}\n",
        html=email_layout([html.escape(line) for line in lines], link, action),
    )


def _message(
    context: EmailContext, user_id: UserId, batch: Sequence[Notification]
) -> EmailMessage | None:
    readers = context.readers
    address = readers.directory.email_addresses([user_id]).get(user_id)
    if address is None:
        return None
    newest = batch[-1]
    project = readers.projects(newest.project_id)
    if newest.kind not in DISCUSSION_KINDS:
        return jira_email(
            to=address,
            notification=newest,
            project="your project" if project is None else project.name,
            link=notification_link(context.base_url, newest),
        )
    return notification_email(
        to=address,
        batch=batch,
        actor=readers.directory.display_names([newest.actor_id]).get(
            newest.actor_id, "A former member"
        ),
        item=_item_title(readers.items, newest.project_id, newest.item_id),
        project="your project" if project is None else project.name,
        link=notification_link(context.base_url, newest),
    )


def _item_title(items: ItemReader, project_id: ProjectId, item_id: UUID | None) -> str:
    if item_id is None:
        return GENERAL_DISCUSSION
    found = items.describe(project_id, [item_id]).get(item_id)
    return "a backlog item" if found is None else found.title


def _deliver(sender: EmailSender, message: EmailMessage) -> bool:
    for attempt in range(1, SEND_ATTEMPTS + 1):
        try:
            sender.send(message)
        except EmailSendError as error:
            # By kind only: the message holds the address and the link.
            logger.warning(
                "Notification email not sent", extra={"attempt": attempt, "error": str(error)}
            )
        else:
            return True
    return False


def _line(name: str) -> str:
    return " ".join(name.split())
