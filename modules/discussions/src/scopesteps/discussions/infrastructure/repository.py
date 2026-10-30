from collections.abc import Collection
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, and_, func, or_, select, update
from sqlalchemy.orm import Session

from scopesteps.backlog.client import ItemId, ItemSummary, current_version_id, describe_items
from scopesteps.discussions.application.threads import ListCursor, Receipt, ThreadStatus
from scopesteps.discussions.domain.ids import CommentId, ThreadId
from scopesteps.discussions.domain.thread import Comment, Thread
from scopesteps.discussions.infrastructure.orm import (
    CommandReceiptRecord,
    CommentRecord,
    ThreadRecord,
)
from scopesteps.identity.client import UserId
from scopesteps.kernel.ids import new_id
from scopesteps.projects.client import ProjectId


class SqlThreadStore:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, thread_id: ThreadId) -> Thread | None:
        record = self._session.get(ThreadRecord, thread_id, populate_existing=True)
        return None if record is None else _to_thread(record)

    def add(self, thread: Thread) -> None:
        self._session.add(
            ThreadRecord(
                id=thread.id,
                project_id=thread.project_id,
                item_id=thread.item_id,
                created_by=thread.created_by,
                created_at=thread.created_at,
                last_activity_at=thread.last_activity_at,
                open_comments=thread.open_comments,
                revision=thread.revision,
                resolved_at=thread.resolved_at,
                resolved_by=thread.resolved_by,
                resolved_by_name=thread.resolved_by_name,
            )
        )
        self._session.flush()

    def save(self, thread: Thread, *, expected_revision: int) -> bool:
        result = self._session.execute(
            update(ThreadRecord)
            .where(ThreadRecord.id == thread.id, ThreadRecord.revision == expected_revision)
            .values(
                revision=thread.revision,
                resolved_at=thread.resolved_at,
                resolved_by=thread.resolved_by,
                resolved_by_name=thread.resolved_by_name,
            )
            .execution_options(synchronize_session=False)
        )
        return cast(CursorResult[Any], result).rowcount == 1

    def record_comment(
        self, thread_id: ThreadId, *, open_comments_change: int, activity_at: datetime | None
    ) -> None:
        # Incremented in SQL, so two replies at once both count.
        values: dict[str, Any] = {
            "open_comments": ThreadRecord.open_comments + open_comments_change
        }
        if activity_at is not None:
            values["last_activity_at"] = activity_at
        self._session.execute(
            update(ThreadRecord)
            .where(ThreadRecord.id == thread_id)
            .values(**values)
            .execution_options(synchronize_session=False)
        )

    def newest_activity_first(
        self,
        project_id: ProjectId,
        *,
        item_id: UUID | None,
        general_only: bool,
        status: ThreadStatus,
        after: ListCursor | None,
        limit: int,
    ) -> list[Thread]:
        query = select(ThreadRecord).where(
            ThreadRecord.project_id == project_id, ThreadRecord.open_comments > 0
        )
        if general_only:
            query = query.where(ThreadRecord.item_id.is_(None))
        elif item_id is not None:
            query = query.where(ThreadRecord.item_id == item_id)
        if status == "open":
            query = query.where(ThreadRecord.resolved_at.is_(None))
        elif status == "resolved":
            query = query.where(ThreadRecord.resolved_at.is_not(None))
        if after is not None:
            query = query.where(
                or_(
                    ThreadRecord.last_activity_at < after.last_activity_at,
                    and_(
                        ThreadRecord.last_activity_at == after.last_activity_at,
                        ThreadRecord.id < after.id,
                    ),
                )
            )
        records = self._session.scalars(
            query.order_by(ThreadRecord.last_activity_at.desc(), ThreadRecord.id.desc())
            .limit(limit)
            .execution_options(populate_existing=True)
        )
        return [_to_thread(record) for record in records]

    def open_counts(self, project_id: ProjectId) -> dict[UUID | None, int]:
        rows = self._session.execute(
            select(ThreadRecord.item_id, func.count(ThreadRecord.id))
            .where(
                ThreadRecord.project_id == project_id,
                ThreadRecord.open_comments > 0,
                ThreadRecord.resolved_at.is_(None),
            )
            .group_by(ThreadRecord.item_id)
        )
        return dict(rows.tuples().all())


class SqlCommentStore:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, comment_id: CommentId) -> Comment | None:
        record = self._session.get(CommentRecord, comment_id, populate_existing=True)
        return None if record is None else _to_comment(record)

    def of_thread(self, thread_id: ThreadId) -> list[Comment]:
        return self.of_threads([thread_id]).get(thread_id, [])

    def of_threads(self, thread_ids: Collection[ThreadId]) -> dict[ThreadId, list[Comment]]:
        if not thread_ids:
            return {}
        records = self._session.scalars(
            select(CommentRecord)
            .where(CommentRecord.thread_id.in_(list(thread_ids)))
            .order_by(CommentRecord.thread_id, CommentRecord.created_at, CommentRecord.id)
            .execution_options(populate_existing=True)
        )
        found: dict[ThreadId, list[Comment]] = {}
        for record in records:
            found.setdefault(ThreadId(record.thread_id), []).append(_to_comment(record))
        return found

    def add(self, comment: Comment) -> None:
        self._session.add(
            CommentRecord(
                id=comment.id,
                thread_id=comment.thread_id,
                project_id=comment.project_id,
                author_id=comment.author_id,
                author_name=comment.author_name,
                body=comment.body,
                backlog_version_id=comment.backlog_version_id,
                revision=comment.revision,
                created_at=comment.created_at,
                edited_at=comment.edited_at,
                deleted_at=comment.deleted_at,
            )
        )
        self._session.flush()

    def save(self, comment: Comment, *, expected_revision: int) -> bool:
        result = self._session.execute(
            update(CommentRecord)
            .where(CommentRecord.id == comment.id, CommentRecord.revision == expected_revision)
            .values(
                body=comment.body,
                revision=comment.revision,
                edited_at=comment.edited_at,
                deleted_at=comment.deleted_at,
            )
            .execution_options(synchronize_session=False)
        )
        return cast(CursorResult[Any], result).rowcount == 1

    def posted_since(self, project_id: ProjectId, author_id: UserId, since: datetime) -> int:
        return (
            self._session.scalar(
                select(func.count(CommentRecord.id)).where(
                    CommentRecord.project_id == project_id,
                    CommentRecord.author_id == author_id,
                    CommentRecord.created_at >= since,
                )
            )
            or 0
        )


class SqlReceiptStore:
    def __init__(self, session: Session) -> None:
        self._session = session

    def find(self, actor_id: UserId, idempotency_key: str) -> Receipt | None:
        record = self._session.scalars(
            select(CommandReceiptRecord).where(
                CommandReceiptRecord.actor_id == actor_id,
                CommandReceiptRecord.idempotency_key == idempotency_key,
            )
        ).one_or_none()
        if record is None:
            return None
        return Receipt(
            actor_id=UserId(record.actor_id),
            idempotency_key=record.idempotency_key,
            fingerprint=record.fingerprint,
            thread_id=ThreadId(record.thread_id),
            created_at=record.created_at,
        )

    def add(self, receipt: Receipt) -> None:
        self._session.add(
            CommandReceiptRecord(
                id=new_id(),
                actor_id=receipt.actor_id,
                idempotency_key=receipt.idempotency_key,
                fingerprint=receipt.fingerprint,
                thread_id=receipt.thread_id,
                created_at=receipt.created_at,
            )
        )


class BacklogItems:
    """`BacklogReader` over `backlog`'s client: item names and the current version, read only."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def describe(
        self, project_id: ProjectId, item_ids: Collection[UUID]
    ) -> dict[UUID, ItemSummary]:
        found = describe_items(self._session, project_id, [ItemId(i) for i in item_ids])
        # Not dict(found): that keeps the ItemId key type, which the port widens to UUID.
        return {item_id: summary for item_id, summary in found.items()}  # noqa: C416

    def current_version(self, project_id: ProjectId) -> UUID | None:
        return current_version_id(self._session, project_id)


def _to_thread(record: ThreadRecord) -> Thread:
    return Thread(
        id=ThreadId(record.id),
        project_id=ProjectId(record.project_id),
        item_id=record.item_id,
        created_by=UserId(record.created_by),
        created_at=record.created_at,
        last_activity_at=record.last_activity_at,
        open_comments=record.open_comments,
        revision=record.revision,
        resolved_at=record.resolved_at,
        resolved_by=None if record.resolved_by is None else UserId(record.resolved_by),
        resolved_by_name=record.resolved_by_name,
    )


def _to_comment(record: CommentRecord) -> Comment:
    return Comment(
        id=CommentId(record.id),
        thread_id=ThreadId(record.thread_id),
        project_id=ProjectId(record.project_id),
        author_id=UserId(record.author_id),
        author_name=record.author_name,
        body=record.body,
        backlog_version_id=record.backlog_version_id,
        created_at=record.created_at,
        revision=record.revision,
        edited_at=record.edited_at,
        deleted_at=record.deleted_at,
    )
