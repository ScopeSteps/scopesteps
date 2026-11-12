from collections.abc import Collection, Sequence
from datetime import datetime
from typing import Any, cast, get_args
from uuid import UUID

from sqlalchemy import CursorResult, and_, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from scopesteps.backlog.client import ItemId, ItemSummary, describe_items
from scopesteps.identity.client import UserId
from scopesteps.notifications.application.notifications import ListCursor
from scopesteps.notifications.domain.ids import NotificationId
from scopesteps.notifications.domain.notification import (
    DISCUSSION_KINDS,
    EmailSettings,
    Notification,
    NotificationKind,
)
from scopesteps.notifications.infrastructure.orm import (
    EmailSettingsRecord,
    EmailWindowRecord,
    NotificationRecord,
)
from scopesteps.projects.client import ProjectId

# One tick's work; what is left waits for the next tick.
_EMAIL_BATCH = 500


class SqlNotificationStore:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, notifications: Sequence[Notification]) -> None:
        self._session.add_all(
            NotificationRecord(
                id=n.id,
                user_id=n.user_id,
                project_id=n.project_id,
                item_id=n.item_id,
                thread_id=n.thread_id,
                comment_id=n.comment_id,
                subject_id=n.subject_id,
                version_id=n.version_id,
                details=None if n.details is None else dict(n.details),
                kind=n.kind,
                actor_id=n.actor_id,
                created_at=n.created_at,
                read_at=n.read_at,
                email_waiting=True,
            )
            for n in notifications
        )
        self._session.flush()

    def get(self, notification_id: NotificationId) -> Notification | None:
        record = self._session.get(NotificationRecord, notification_id, populate_existing=True)
        return None if record is None else _to_notification(record)

    def already_told(self, about: UUID, kind: NotificationKind) -> set[UserId]:
        column = (
            NotificationRecord.comment_id
            if kind in DISCUSSION_KINDS
            else NotificationRecord.subject_id
        )
        rows = self._session.scalars(
            select(NotificationRecord.user_id).where(
                column == about, NotificationRecord.kind == kind
            )
        )
        return {UserId(user_id) for user_id in rows}

    def newest_first(
        self,
        user_id: UserId,
        project_ids: Collection[ProjectId],
        *,
        unread_only: bool,
        after: ListCursor | None,
        limit: int,
    ) -> list[Notification]:
        query = select(NotificationRecord).where(
            NotificationRecord.user_id == user_id,
            NotificationRecord.project_id.in_(list(project_ids)),
        )
        if unread_only:
            query = query.where(NotificationRecord.read_at.is_(None))
        if after is not None:
            query = query.where(
                or_(
                    NotificationRecord.created_at < after.created_at,
                    and_(
                        NotificationRecord.created_at == after.created_at,
                        NotificationRecord.id < after.id,
                    ),
                )
            )
        records = self._session.scalars(
            query.order_by(NotificationRecord.created_at.desc(), NotificationRecord.id.desc())
            .limit(limit)
            .execution_options(populate_existing=True)
        )
        return [_to_notification(record) for record in records]

    def unread_count(self, user_id: UserId, project_ids: Collection[ProjectId]) -> int:
        return (
            self._session.scalar(
                select(func.count(NotificationRecord.id)).where(
                    NotificationRecord.user_id == user_id,
                    NotificationRecord.project_id.in_(list(project_ids)),
                    NotificationRecord.read_at.is_(None),
                )
            )
            or 0
        )

    def mark_read(self, notification_id: NotificationId, now: datetime) -> None:
        self._session.execute(
            update(NotificationRecord)
            .where(NotificationRecord.id == notification_id, NotificationRecord.read_at.is_(None))
            .values(read_at=now)
            .execution_options(synchronize_session=False)
        )

    def mark_all_read(self, user_id: UserId, now: datetime) -> None:
        self._session.execute(
            update(NotificationRecord)
            .where(NotificationRecord.user_id == user_id, NotificationRecord.read_at.is_(None))
            .values(read_at=now)
            .execution_options(synchronize_session=False)
        )

    def delete_of_comment(self, comment_id: UUID) -> None:
        self._session.execute(
            delete(NotificationRecord)
            .where(NotificationRecord.comment_id == comment_id)
            .execution_options(synchronize_session=False)
        )

    def delete_older_than(self, cutoff: datetime) -> int:
        result = self._session.execute(
            delete(NotificationRecord)
            .where(NotificationRecord.created_at < cutoff)
            .execution_options(synchronize_session=False)
        )
        self._session.execute(
            delete(EmailWindowRecord)
            .where(EmailWindowRecord.last_sent_at < cutoff)
            .execution_options(synchronize_session=False)
        )
        return cast(CursorResult[Any], result).rowcount


class SqlSettingsStore:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, user_id: UserId) -> EmailSettings | None:
        record = self._session.get(EmailSettingsRecord, user_id, populate_existing=True)
        return None if record is None else _to_settings(record)

    def many(self, user_ids: Collection[UserId]) -> dict[UserId, EmailSettings]:
        if not user_ids:
            return {}
        records = self._session.scalars(
            select(EmailSettingsRecord).where(EmailSettingsRecord.user_id.in_(list(user_ids)))
        )
        return {UserId(record.user_id): _to_settings(record) for record in records}

    def save(self, user_id: UserId, settings: EmailSettings) -> None:
        self._session.merge(
            EmailSettingsRecord(
                user_id=user_id,
                email_on_mention=settings.email_on_mention,
                email_on_reply=settings.email_on_reply,
                email_on_jira_failure=settings.email_on_jira_failure,
            )
        )


class SqlEmailQueue:
    def __init__(self, session: Session) -> None:
        self._session = session

    def waiting(self) -> list[Notification]:
        records = self._session.scalars(
            select(NotificationRecord)
            .where(NotificationRecord.email_waiting.is_(True))
            .order_by(NotificationRecord.created_at, NotificationRecord.id)
            .limit(_EMAIL_BATCH)
            .execution_options(populate_existing=True)
        )
        return [_to_notification(record) for record in records]

    def last_sent(self, user_id: UserId, topic_id: UUID) -> datetime | None:
        return self._session.scalar(
            select(EmailWindowRecord.last_sent_at).where(
                EmailWindowRecord.user_id == user_id, EmailWindowRecord.thread_id == topic_id
            )
        )

    def claim_window(
        self, user_id: UserId, topic_id: UUID, *, seen: datetime | None, now: datetime
    ) -> bool:
        if seen is None:
            try:
                with self._session.begin_nested():
                    self._session.add(
                        EmailWindowRecord(user_id=user_id, thread_id=topic_id, last_sent_at=now)
                    )
            except IntegrityError:
                return False
            return True
        result = self._session.execute(
            update(EmailWindowRecord)
            .where(
                EmailWindowRecord.user_id == user_id,
                EmailWindowRecord.thread_id == topic_id,
                EmailWindowRecord.last_sent_at == seen,
            )
            .values(last_sent_at=now)
            .execution_options(synchronize_session=False)
        )
        return cast(CursorResult[Any], result).rowcount == 1

    def settle(self, notification_ids: Collection[NotificationId]) -> None:
        self._session.execute(
            update(NotificationRecord)
            .where(NotificationRecord.id.in_(list(notification_ids)))
            .values(email_waiting=False)
            .execution_options(synchronize_session=False)
        )

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()


class BacklogItems:
    """`ItemReader` over `backlog`'s client."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def describe(
        self, project_id: ProjectId, item_ids: Collection[UUID]
    ) -> dict[UUID, ItemSummary]:
        found = describe_items(self._session, project_id, [ItemId(i) for i in item_ids])
        # Not dict(found): that keeps the ItemId key type, which the port widens to UUID.
        return {item_id: summary for item_id, summary in found.items()}  # noqa: C416


def _to_notification(record: NotificationRecord) -> Notification:
    return Notification(
        id=NotificationId(record.id),
        user_id=UserId(record.user_id),
        project_id=ProjectId(record.project_id),
        item_id=record.item_id,
        thread_id=record.thread_id,
        comment_id=record.comment_id,
        kind=_kind(record.kind),
        actor_id=UserId(record.actor_id),
        created_at=record.created_at,
        read_at=record.read_at,
        subject_id=record.subject_id,
        version_id=record.version_id,
        details=record.details,
    )


def _kind(stored: str) -> NotificationKind:
    for kind in get_args(NotificationKind):
        if kind == stored:
            return cast(NotificationKind, kind)
    raise ValueError(f"Unknown notification kind {stored!r}")


def _to_settings(record: EmailSettingsRecord) -> EmailSettings:
    return EmailSettings(
        email_on_mention=record.email_on_mention,
        email_on_reply=record.email_on_reply,
        email_on_jira_failure=record.email_on_jira_failure,
    )
