"""Recording notifications and reading them back. Each person sees only their own, and only for
projects they are still a member of (ADR 0021)."""

import base64
import binascii
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from scopesteps.backlog.client import ItemSummary
from scopesteps.identity.client import Actor, UserDirectory, UserId
from scopesteps.kernel.errors import InvalidInputError, NotFoundError
from scopesteps.kernel.ids import new_id
from scopesteps.notifications.domain.ids import NotificationId
from scopesteps.notifications.domain.notification import (
    RETENTION,
    EmailSettings,
    Notification,
    NotificationKind,
)
from scopesteps.projects.client import ProjectId, ProjectReader

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 50


class InvalidCursorError(InvalidInputError):
    code = "INVALID_CURSOR"


@dataclass(frozen=True)
class ListCursor:
    created_at: datetime
    id: NotificationId


class NotificationStore(Protocol):
    """Writes join the caller's transaction; the caller commits."""

    def add(self, notifications: Sequence[Notification]) -> None: ...

    def get(self, notification_id: NotificationId) -> Notification | None: ...

    def already_told(self, comment_id: UUID, kind: NotificationKind) -> set[UserId]:
        """Who already has a notification of this kind about the comment."""
        ...

    def newest_first(
        self,
        user_id: UserId,
        project_ids: Collection[ProjectId],
        *,
        unread_only: bool,
        after: ListCursor | None,
        limit: int,
    ) -> list[Notification]: ...

    def unread_count(self, user_id: UserId, project_ids: Collection[ProjectId]) -> int: ...

    def mark_read(self, notification_id: NotificationId, now: datetime) -> None: ...

    def mark_all_read(self, user_id: UserId, now: datetime) -> None: ...

    def delete_of_comment(self, comment_id: UUID) -> None: ...

    def delete_older_than(self, cutoff: datetime) -> int: ...


class SettingsStore(Protocol):
    def get(self, user_id: UserId) -> EmailSettings | None: ...

    def many(self, user_ids: Collection[UserId]) -> dict[UserId, EmailSettings]: ...

    def save(self, user_id: UserId, settings: EmailSettings) -> None: ...


class ItemReader(Protocol):
    def describe(
        self, project_id: ProjectId, item_ids: Collection[UUID]
    ) -> dict[UUID, ItemSummary]: ...


@dataclass(frozen=True)
class Readers:
    directory: UserDirectory
    projects: ProjectReader
    items: ItemReader


@dataclass(frozen=True)
class NewNotification:
    """`recipient` hears that `actor_id` wrote comment `comment_id`. The caller has decided who
    is told, and never tells someone about their own comment."""

    recipient: UserId
    kind: NotificationKind
    project_id: ProjectId
    item_id: UUID | None
    thread_id: UUID
    comment_id: UUID
    actor_id: UserId
    created_at: datetime


@dataclass(frozen=True)
class NotificationView:
    notification: Notification
    actor_name: str
    project_name: str
    item: ItemSummary | None


@dataclass(frozen=True)
class NotificationPage:
    notifications: tuple[NotificationView, ...]
    next_cursor: str | None


def record_notifications(store: NotificationStore, new: Sequence[NewNotification]) -> None:
    """Keep the ones that are news, in the caller's transaction: taking a mention out of a comment
    and putting it back tells nobody twice."""
    told: dict[tuple[UUID, NotificationKind], set[UserId]] = {}
    fresh: list[Notification] = []
    for n in new:
        key = (n.comment_id, n.kind)
        if key not in told:
            told[key] = store.already_told(*key)
        if n.recipient not in told[key]:
            told[key].add(n.recipient)
            fresh.append(
                Notification(
                    id=NotificationId(new_id()),
                    user_id=n.recipient,
                    project_id=n.project_id,
                    item_id=n.item_id,
                    thread_id=n.thread_id,
                    comment_id=n.comment_id,
                    kind=n.kind,
                    actor_id=n.actor_id,
                    created_at=n.created_at,
                )
            )
    store.add(fresh)


def list_notifications(
    store: NotificationStore,
    readers: Readers,
    actor: Actor,
    *,
    unread_only: bool,
    cursor: str | None,
    limit: int,
) -> NotificationPage:
    """Newest first. A project the actor left is gone from the list while they are out of it."""
    member_of = readers.directory.project_ids(actor.user_id)
    # One extra row tells whether an older page exists without a count query.
    rows = store.newest_first(
        actor.user_id,
        member_of,
        unread_only=unread_only,
        after=None if cursor is None else decode_cursor(cursor),
        limit=limit + 1,
    )
    page = rows[:limit]
    names = readers.directory.display_names({n.actor_id for n in page})
    items = _items(readers.items, page)
    projects = {
        project_id: ref.name if (ref := readers.projects(project_id)) is not None else ""
        for project_id in {n.project_id for n in page}
    }
    last = page[-1] if page else None
    return NotificationPage(
        notifications=tuple(
            NotificationView(
                notification=n,
                actor_name=names.get(n.actor_id, "A former member"),
                project_name=projects[n.project_id],
                item=None if n.item_id is None else items.get((n.project_id, n.item_id)),
            )
            for n in page
        ),
        next_cursor=encode_cursor(ListCursor(last.created_at, last.id))
        if last is not None and len(rows) > limit
        else None,
    )


def unread_count(store: NotificationStore, directory: UserDirectory, actor: Actor) -> int:
    return store.unread_count(actor.user_id, directory.project_ids(actor.user_id))


def mark_read(
    store: NotificationStore,
    directory: UserDirectory,
    actor: Actor,
    notification_id: NotificationId,
    now: datetime,
) -> None:
    """Reading a notification twice keeps the first time. Anyone else's, or one of a project the
    actor left, is reported like one that does not exist."""
    notification = store.get(notification_id)
    if (
        notification is None
        or notification.user_id != actor.user_id
        or notification.project_id not in directory.project_ids(actor.user_id)
    ):
        raise NotFoundError("Notification not found")
    if notification.read_at is None:
        store.mark_read(notification_id, now)


def mark_all_read(store: NotificationStore, actor: Actor, now: datetime) -> None:
    store.mark_all_read(actor.user_id, now)


def get_settings(store: SettingsStore, actor: Actor) -> EmailSettings:
    return store.get(actor.user_id) or EmailSettings()


def save_settings(store: SettingsStore, actor: Actor, settings: EmailSettings) -> EmailSettings:
    store.save(actor.user_id, settings)
    return settings


def delete_expired(store: NotificationStore, now: datetime) -> int:
    return store.delete_older_than(now - RETENTION)


def encode_cursor(cursor: ListCursor) -> str:
    raw = f"{cursor.created_at.isoformat()}|{cursor.id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(value: str) -> ListCursor:
    try:
        at, _, notification_id = base64.urlsafe_b64decode(value).decode().partition("|")
        cursor = ListCursor(datetime.fromisoformat(at), NotificationId(UUID(notification_id)))
    except (ValueError, binascii.Error) as error:
        raise InvalidCursorError("The cursor is not one this list returned") from error
    if cursor.created_at.tzinfo is None:
        raise InvalidCursorError("The cursor is not one this list returned")
    return cursor


def _items(
    items: ItemReader, notifications: Sequence[Notification]
) -> Mapping[tuple[ProjectId, UUID], ItemSummary]:
    wanted: dict[ProjectId, set[UUID]] = {}
    for n in notifications:
        if n.item_id is not None:
            wanted.setdefault(n.project_id, set()).add(n.item_id)
    return {
        (project_id, item_id): summary
        for project_id, item_ids in wanted.items()
        for item_id, summary in items.describe(project_id, item_ids).items()
    }
