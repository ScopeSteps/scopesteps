"""Notification emails: batched per person and thread, sent after the commit that claimed them.

A batch is claimed by moving the person's window for the thread, so two API processes cannot send
the same email. A send that still fails on its one retry is logged and dropped: the in-app
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
    EMAIL_WINDOW,
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

    def last_sent(self, user_id: UserId, thread_id: UUID) -> datetime | None: ...

    def claim_window(
        self, user_id: UserId, thread_id: UUID, *, seen: datetime | None, now: datetime
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
    """One email for each person and thread whose window is open. What arrives inside a window
    waits for its end and goes out as one batch, unless it stopped being news. Returns how many
    emails were sent."""
    batches: dict[tuple[UserId, UUID], list[Notification]] = {}
    for notification in queue.waiting():
        batches.setdefault((notification.user_id, notification.thread_id), []).append(notification)
    settings = context.settings.many({user_id for user_id, _ in batches})
    sent = 0
    for (user_id, thread_id), waiting in batches.items():
        last = queue.last_sent(user_id, thread_id)
        if last is not None and now - last < EMAIL_WINDOW:
            continue
        chosen = worth_emailing(
            waiting,
            settings.get(user_id, EmailSettings()),
            context.readers.directory.project_ids(user_id),
        )
        message = _message(context, user_id, chosen) if chosen else None
        if message is not None and not queue.claim_window(user_id, thread_id, seen=last, now=now):
            queue.rollback()
            continue
        queue.settle([n.id for n in waiting])
        queue.commit()
        if message is not None and _deliver(context.sender, message):
            sent += 1
    return sent


def notification_link(base_url: str, notification: Notification) -> str:
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


def _message(
    context: EmailContext, user_id: UserId, batch: Sequence[Notification]
) -> EmailMessage | None:
    readers = context.readers
    address = readers.directory.email_addresses([user_id]).get(user_id)
    if address is None:
        return None
    newest = batch[-1]
    project = readers.projects(newest.project_id)
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
