"""Starting, reading, replying to, editing, deleting, resolving and reopening discussions.

Every member of the project may read and post; only an author edits or deletes their comment;
the thread's author, an editor or an approver resolves it, and anyone reopens it. A project the
actor is not a member of is reported exactly like a thread that does not exist.
"""

import base64
import binascii
import hashlib
import json
from collections.abc import Collection, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Literal, Protocol
from uuid import UUID

from scopesteps.audit.client import AuditActor, AuditRecorder, EventType, Subject, SubjectKind
from scopesteps.backlog.client import ItemSummary
from scopesteps.discussions.domain.ids import CommentId, ThreadId
from scopesteps.discussions.domain.thread import (
    Comment,
    CommentChangedError,
    ItemNotFoundError,
    Thread,
    ThreadChangedError,
    ThreadResolvedError,
    comment_body,
    visible_comments,
)
from scopesteps.identity.client import (
    ProjectAccess,
    ProjectAccessResolver,
    Role,
    UserId,
)
from scopesteps.kernel.errors import (
    ConflictError,
    InvalidInputError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitedError,
)
from scopesteps.kernel.ids import new_id
from scopesteps.projects.client import ProjectId

COMMENTS_PER_MINUTE = 30
"""Per member and project: well above anyone typing, low enough to stop a script flooding a
project's discussions."""

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 50

# Item titles run to 200 characters, the whole summary may not.
_SUMMARY_TITLE_CHARS = 120

ThreadStatus = Literal["open", "resolved", "all"]


class IdempotencyKeyReusedError(ConflictError):
    code = "IDEMPOTENCY_KEY_REUSED"


class InvalidCursorError(InvalidInputError):
    code = "INVALID_CURSOR"


@dataclass(frozen=True)
class ListCursor:
    last_activity_at: datetime
    id: ThreadId


class ThreadStore(Protocol):
    """Writes join the caller's transaction; the caller commits."""

    def get(self, thread_id: ThreadId) -> Thread | None: ...

    def add(self, thread: Thread) -> None: ...

    def save(self, thread: Thread, *, expected_revision: int) -> bool:
        """Compare-and-set on the revision: False, and nothing written, if it moved."""
        ...

    def record_comment(
        self, thread_id: ThreadId, *, open_comments_change: int, activity_at: datetime | None
    ) -> None:
        """Count a comment posted or deleted, without touching the revision, so a reply never
        makes someone's resolve stale."""
        ...

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
        """Threads that still have a comment, by last activity then id, both descending."""
        ...

    def open_counts(self, project_id: ProjectId) -> dict[UUID | None, int]:
        """Open threads per item, None for General discussion; items with none are absent."""
        ...


class CommentStore(Protocol):
    def get(self, comment_id: CommentId) -> Comment | None: ...

    def of_thread(self, thread_id: ThreadId) -> list[Comment]:
        """Oldest first, deleted ones included."""
        ...

    def of_threads(self, thread_ids: Collection[ThreadId]) -> dict[ThreadId, list[Comment]]:
        """`of_thread` for many threads in one query."""
        ...

    def add(self, comment: Comment) -> None: ...

    def save(self, comment: Comment, *, expected_revision: int) -> bool:
        """Compare-and-set on the revision: False, and nothing written, if it moved."""
        ...

    def posted_since(self, project_id: ProjectId, author_id: UserId, since: datetime) -> int: ...


class BacklogReader(Protocol):
    def describe(
        self, project_id: ProjectId, item_ids: Collection[UUID]
    ) -> dict[UUID, ItemSummary]:
        """The items the project ever had among `item_ids`."""
        ...

    def current_version(self, project_id: ProjectId) -> UUID | None: ...


@dataclass(frozen=True)
class Receipt:
    actor_id: UserId
    idempotency_key: str
    fingerprint: str
    thread_id: ThreadId
    created_at: datetime


class ReceiptStore(Protocol):
    def find(self, actor_id: UserId, idempotency_key: str) -> Receipt | None: ...

    def add(self, receipt: Receipt) -> None: ...


@dataclass(frozen=True)
class Ports:
    threads: ThreadStore
    comments: CommentStore
    backlog: BacklogReader
    receipts: ReceiptStore
    audit: AuditRecorder


@dataclass(frozen=True)
class ThreadView:
    thread: Thread
    comments: tuple[Comment, ...]
    """As everyone sees them: oldest first, see `visible_comments`."""
    item: ItemSummary | None
    """None for General discussion."""


@dataclass(frozen=True)
class ThreadPage:
    threads: tuple[ThreadView, ...]
    next_cursor: str | None


@dataclass(frozen=True)
class OpenCounts:
    items: Mapping[UUID, int]
    general: int


def start_thread(
    ports: Ports,
    access: ProjectAccess,
    *,
    idempotency_key: str,
    item_id: UUID | None,
    body: str,
    now: datetime,
) -> ThreadView:
    access.require_member()
    text = comment_body(body)
    command = _fingerprint("thread.start", access.project_id, item_id, text)
    replayed = _replayed(ports.receipts, access.actor.user_id, idempotency_key, command)
    if replayed is not None:
        return _view(ports, _thread_or_404(ports, replayed))
    item = None
    if item_id is not None:
        item = ports.backlog.describe(access.project_id, [item_id]).get(item_id)
        if item is None or not item.in_current_backlog:
            raise ItemNotFoundError("No epic or story with this id is in the current backlog")
    _check_rate(ports.comments, access, now)

    thread = Thread(
        id=ThreadId(new_id()),
        project_id=access.project_id,
        item_id=item_id,
        created_by=access.actor.user_id,
        created_at=now,
        last_activity_at=now,
        open_comments=1,
    )
    ports.threads.add(thread)
    ports.comments.add(_comment(ports, access, thread.id, text, now))
    _audit(ports.audit, access, EventType.THREAD_STARTED, "Started", thread, item, now)
    _add_receipt(ports.receipts, access, idempotency_key, command, thread.id, now)
    return _view(ports, thread)


def reply(
    ports: Ports,
    resolve: ProjectAccessResolver,
    thread_id: ThreadId,
    *,
    idempotency_key: str,
    body: str,
    now: datetime,
) -> ThreadView:
    thread, access = _readable(ports, resolve, thread_id)
    text = comment_body(body)
    command = _fingerprint("thread.reply", access.project_id, thread_id, text)
    if _replayed(ports.receipts, access.actor.user_id, idempotency_key, command) is not None:
        return _view(ports, _thread_or_404(ports, thread_id))
    if thread.resolved:
        raise ThreadResolvedError("This discussion is resolved. Reopen it to reply.")
    _check_rate(ports.comments, access, now)

    ports.comments.add(_comment(ports, access, thread_id, text, now))
    ports.threads.record_comment(thread_id, open_comments_change=1, activity_at=now)
    _add_receipt(ports.receipts, access, idempotency_key, command, thread_id, now)
    return _view(ports, _thread_or_404(ports, thread_id))


def edit_comment(
    ports: Ports,
    resolve: ProjectAccessResolver,
    comment_id: CommentId,
    *,
    idempotency_key: str,
    body: str,
    expected_revision: int,
    now: datetime,
) -> ThreadView:
    comment, access = _own_comment(ports, resolve, comment_id)
    text = comment_body(body)
    command = _fingerprint("comment.edit", access.project_id, comment_id, text, expected_revision)
    if _replayed(ports.receipts, access.actor.user_id, idempotency_key, command) is not None:
        return _view(ports, _thread_or_404(ports, comment.thread_id))
    if comment.revision != expected_revision:
        raise _comment_changed(comment)

    if text != comment.body:
        edited = comment.edited(text, now)
        if not ports.comments.save(edited, expected_revision=expected_revision):
            raise _comment_changed(ports.comments.get(comment_id) or comment)
    _add_receipt(ports.receipts, access, idempotency_key, command, comment.thread_id, now)
    return _view(ports, _thread_or_404(ports, comment.thread_id))


def delete_comment(
    ports: Ports, resolve: ProjectAccessResolver, comment_id: CommentId, now: datetime
) -> None:
    """Soft delete: the text is gone from every reader, the row and its author stay. Deleting a
    deleted comment changes nothing."""
    comment, _ = _own_comment(ports, resolve, comment_id)
    if comment.deleted:
        return
    deleted = replace(comment, body="", revision=comment.revision + 1, deleted_at=now)
    if not ports.comments.save(deleted, expected_revision=comment.revision):
        raise _comment_changed(comment)
    ports.threads.record_comment(comment.thread_id, open_comments_change=-1, activity_at=None)


def resolve_thread(
    ports: Ports,
    resolve: ProjectAccessResolver,
    thread_id: ThreadId,
    *,
    idempotency_key: str,
    expected_revision: int,
    now: datetime,
) -> ThreadView:
    thread, access = _readable(ports, resolve, thread_id)
    if thread.created_by != access.actor.user_id:
        access.require_any_role(Role.EDITOR, Role.APPROVER)
    return _change_state(ports, access, thread, "resolve", idempotency_key, expected_revision, now)


def reopen_thread(
    ports: Ports,
    resolve: ProjectAccessResolver,
    thread_id: ThreadId,
    *,
    idempotency_key: str,
    expected_revision: int,
    now: datetime,
) -> ThreadView:
    thread, access = _readable(ports, resolve, thread_id)
    return _change_state(ports, access, thread, "reopen", idempotency_key, expected_revision, now)


def get_thread(ports: Ports, resolve: ProjectAccessResolver, thread_id: ThreadId) -> ThreadView:
    thread, _ = _readable(ports, resolve, thread_id)
    return _view(ports, thread)


def list_threads(
    ports: Ports,
    access: ProjectAccess,
    *,
    item_id: UUID | None,
    general_only: bool,
    status: ThreadStatus,
    cursor: str | None,
    limit: int,
) -> ThreadPage:
    access.require_member()
    # One extra row tells whether an older page exists without a count query.
    threads = ports.threads.newest_activity_first(
        access.project_id,
        item_id=item_id,
        general_only=general_only,
        status=status,
        after=None if cursor is None else decode_cursor(cursor),
        limit=limit + 1,
    )
    page = threads[:limit]
    comments = ports.comments.of_threads([t.id for t in page])
    items = ports.backlog.describe(
        access.project_id, {t.item_id for t in page if t.item_id is not None}
    )
    last = page[-1] if page else None
    return ThreadPage(
        threads=tuple(
            ThreadView(
                thread,
                tuple(visible_comments(comments.get(thread.id, []))),
                None if thread.item_id is None else items.get(thread.item_id),
            )
            for thread in page
        ),
        next_cursor=encode_cursor(ListCursor(last.last_activity_at, last.id))
        if last is not None and len(threads) > limit
        else None,
    )


def open_counts(ports: Ports, access: ProjectAccess) -> OpenCounts:
    access.require_member()
    counts = ports.threads.open_counts(access.project_id)
    return OpenCounts(
        items={item_id: n for item_id, n in counts.items() if item_id is not None},
        general=counts.get(None, 0),
    )


def encode_cursor(cursor: ListCursor) -> str:
    raw = f"{cursor.last_activity_at.isoformat()}|{cursor.id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(value: str) -> ListCursor:
    try:
        at, _, thread_id = base64.urlsafe_b64decode(value).decode().partition("|")
        cursor = ListCursor(datetime.fromisoformat(at), ThreadId(UUID(thread_id)))
    except (ValueError, binascii.Error) as error:
        raise InvalidCursorError("The cursor is not one this list returned") from error
    if cursor.last_activity_at.tzinfo is None:
        raise InvalidCursorError("The cursor is not one this list returned")
    return cursor


def _change_state(
    ports: Ports,
    access: ProjectAccess,
    thread: Thread,
    action: Literal["resolve", "reopen"],
    idempotency_key: str,
    expected_revision: int,
    now: datetime,
) -> ThreadView:
    command = _fingerprint(f"thread.{action}", access.project_id, thread.id, expected_revision)
    if _replayed(ports.receipts, access.actor.user_id, idempotency_key, command) is not None:
        return _view(ports, _thread_or_404(ports, thread.id))
    if thread.revision != expected_revision:
        raise _thread_changed(thread)
    # Resolving a resolved thread, or reopening an open one, is already done: nothing to record.
    if thread.resolved != (action == "resolve"):
        changed = (
            thread.resolve(access.actor.user_id, access.actor.display_name, now)
            if action == "resolve"
            else thread.reopen()
        )
        if not ports.threads.save(changed, expected_revision=expected_revision):
            raise _thread_changed(_thread_or_404(ports, thread.id))
        item = _item(ports, thread)
        if action == "resolve":
            _audit(ports.audit, access, EventType.THREAD_RESOLVED, "Resolved", thread, item, now)
        else:
            _audit(ports.audit, access, EventType.THREAD_REOPENED, "Reopened", thread, item, now)
        thread = changed
    _add_receipt(ports.receipts, access, idempotency_key, command, thread.id, now)
    return _view(ports, thread)


def _readable(
    ports: Ports, resolve: ProjectAccessResolver, thread_id: ThreadId
) -> tuple[Thread, ProjectAccess]:
    thread = ports.threads.get(thread_id)
    access = None if thread is None else resolve(thread.project_id)
    if thread is None or access is None or not access.roles or thread.open_comments == 0:
        raise NotFoundError("Discussion not found")
    return thread, access


def _own_comment(
    ports: Ports, resolve: ProjectAccessResolver, comment_id: CommentId
) -> tuple[Comment, ProjectAccess]:
    comment = ports.comments.get(comment_id)
    thread = None if comment is None else ports.threads.get(comment.thread_id)
    access = None if thread is None else resolve(thread.project_id)
    if comment is None or access is None or not access.roles:
        raise NotFoundError("Comment not found")
    if comment.author_id != access.actor.user_id:
        raise PermissionDeniedError("Only its author can change or delete a comment")
    return comment, access


def _thread_or_404(ports: Ports, thread_id: ThreadId) -> Thread:
    thread = ports.threads.get(thread_id)
    if thread is None:
        raise NotFoundError("Discussion not found")
    return thread


def _view(ports: Ports, thread: Thread) -> ThreadView:
    return ThreadView(
        thread, tuple(visible_comments(ports.comments.of_thread(thread.id))), _item(ports, thread)
    )


def _item(ports: Ports, thread: Thread) -> ItemSummary | None:
    if thread.item_id is None:
        return None
    return ports.backlog.describe(thread.project_id, [thread.item_id]).get(thread.item_id)


def _comment(
    ports: Ports, access: ProjectAccess, thread_id: ThreadId, body: str, now: datetime
) -> Comment:
    return Comment(
        id=CommentId(new_id()),
        thread_id=thread_id,
        project_id=access.project_id,
        author_id=access.actor.user_id,
        author_name=access.actor.display_name,
        body=body,
        backlog_version_id=ports.backlog.current_version(access.project_id),
        created_at=now,
    )


def _check_rate(comments: CommentStore, access: ProjectAccess, now: datetime) -> None:
    posted = comments.posted_since(
        access.project_id, access.actor.user_id, now - timedelta(minutes=1)
    )
    if posted >= COMMENTS_PER_MINUTE:
        raise RateLimitedError(
            "You have posted a lot in the last minute. Wait a moment and try again.",
            details={"limit": COMMENTS_PER_MINUTE, "window_seconds": 60},
        )


def _audit(
    audit: AuditRecorder,
    access: ProjectAccess,
    event: EventType,
    verb: str,
    thread: Thread,
    item: ItemSummary | None,
    now: datetime,
) -> None:
    """Names what the discussion is about, never what anyone wrote in it."""
    if item is None:
        about = "General discussion"
        subjects = (Subject(SubjectKind.THREAD, thread.id),)
    else:
        title = item.title
        if len(title) > _SUMMARY_TITLE_CHARS:
            title = title[: _SUMMARY_TITLE_CHARS - 1].rstrip() + "…"
        about = f"{item.kind} “{title}”"
        subjects = (Subject(SubjectKind.THREAD, thread.id), Subject(SubjectKind.ITEM, item.id))
    audit.record(
        project_id=thread.project_id,
        actor=AuditActor.user(access.actor),
        type=event,
        subjects=subjects,
        summary=f"{verb} a discussion on {about}",
        occurred_at=now,
    )


def _fingerprint(operation: str, *values: object) -> str:
    canonical = json.dumps([operation, *(None if v is None else str(v) for v in values)])
    return hashlib.sha256(canonical.encode()).hexdigest()


def _replayed(
    receipts: ReceiptStore, actor_id: UserId, idempotency_key: str, fingerprint: str
) -> ThreadId | None:
    receipt = receipts.find(actor_id, idempotency_key)
    if receipt is None:
        return None
    if receipt.fingerprint != fingerprint:
        raise IdempotencyKeyReusedError("This Idempotency-Key was already used for another request")
    return receipt.thread_id


def _add_receipt(
    receipts: ReceiptStore,
    access: ProjectAccess,
    idempotency_key: str,
    fingerprint: str,
    thread_id: ThreadId,
    now: datetime,
) -> None:
    receipts.add(Receipt(access.actor.user_id, idempotency_key, fingerprint, thread_id, now))


def _thread_changed(thread: Thread) -> ThreadChangedError:
    return ThreadChangedError(
        "Someone changed this discussion since you loaded it. Reload it and try again.",
        details={"current_revision": thread.revision},
    )


def _comment_changed(comment: Comment) -> CommentChangedError:
    return CommentChangedError(
        "This comment changed since you loaded it. Reload the discussion and try again.",
        details={"current_revision": comment.revision},
    )
