from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from scopesteps.audit.client import audit_recorder
from scopesteps.backlog.client import BacklogVersionId, ItemId
from scopesteps.discussions.application import threads
from scopesteps.discussions.application.threads import Ports, ThreadView
from scopesteps.discussions.client import CommentId, ThreadId
from scopesteps.discussions.http.schemas import (
    CommentResponse,
    EditCommentRequest,
    ItemThreadCount,
    ReplyRequest,
    StartThreadRequest,
    ThreadCountsResponse,
    ThreadItemResponse,
    ThreadPageResponse,
    ThreadResponse,
    ThreadStateRequest,
)
from scopesteps.discussions.infrastructure.repository import (
    BacklogItems,
    SqlCommentStore,
    SqlReceiptStore,
    SqlThreadStore,
)
from scopesteps.identity.client import (
    ProjectAccess,
    ProjectAccessResolver,
    get_project_access,
    get_project_access_resolver,
)
from scopesteps.infrastructure.database import utc_now
from scopesteps.infrastructure.http import ErrorResponse, IdempotencyKey, SessionDep
from scopesteps.kernel.errors import ConflictError
from scopesteps.projects.client import ProjectId

router = APIRouter(tags=["discussions"])

AccessDep = Annotated[ProjectAccess, Depends(get_project_access)]
ResolverDep = Annotated[ProjectAccessResolver, Depends(get_project_access_resolver)]

RATE_LIMITED: dict[int | str, dict[str, Any]] = {
    429: {
        "model": ErrorResponse,
        "description": "`RATE_LIMITED`: more than 30 comments from you in this project in the "
        "last minute.",
    }
}


class ConcurrentCommandError(ConflictError):
    code = "DISCUSSION_COMMAND_IN_PROGRESS"


@router.get("/projects/{project_id}/threads")
def list_threads(
    project_id: ProjectId,
    access: AccessDep,
    session: SessionDep,
    item_id: Annotated[
        ItemId | None, Query(description="Only the threads on this epic or story.")
    ] = None,
    general: Annotated[bool, Query(description="Only General discussion threads.")] = False,
    thread_status: Annotated[Literal["open", "resolved", "all"], Query(alias="status")] = "all",
    limit: Annotated[int, Query(ge=1, le=threads.MAX_PAGE_SIZE)] = threads.DEFAULT_PAGE_SIZE,
    cursor: Annotated[
        str | None, Query(max_length=200, description="`next_cursor` of the previous page.")
    ] = None,
) -> ThreadPageResponse:
    """The project's discussions, newest activity first, each with all its comments. Any member
    may read them."""
    page = threads.list_threads(
        _ports(session),
        access,
        item_id=item_id,
        general_only=general,
        status=thread_status,
        cursor=cursor,
        limit=limit,
    )
    return ThreadPageResponse(
        threads=[_thread(view) for view in page.threads], next_cursor=page.next_cursor
    )


@router.get("/projects/{project_id}/threads/counts")
def thread_counts(
    project_id: ProjectId, access: AccessDep, session: SessionDep
) -> ThreadCountsResponse:
    """Open threads per epic or story, and in General discussion, for the backlog list."""
    counts = threads.open_counts(_ports(session), access)
    return ThreadCountsResponse(
        items=[ItemThreadCount(item_id=i, open_threads=n) for i, n in counts.items.items()],
        general_open_threads=counts.general,
    )


@router.post(
    "/projects/{project_id}/threads", status_code=status.HTTP_201_CREATED, responses=RATE_LIMITED
)
def start_thread(
    project_id: ProjectId,
    body: StartThreadRequest,
    idempotency_key: IdempotencyKey,
    access: AccessDep,
    session: SessionDep,
) -> ThreadResponse:
    """Start a discussion on an epic or story in the current backlog, or in General discussion,
    with its first comment. Any member may. 404 `ITEM_NOT_FOUND` for an item not in the current
    backlog; 422 `COMMENT_EMPTY` or `COMMENT_TOO_LONG`. It never changes the backlog."""
    view = threads.start_thread(
        _ports(session),
        access,
        idempotency_key=idempotency_key,
        item_id=body.item_id,
        body=body.body,
        now=utc_now(),
    )
    _commit(session)
    return _thread(view)


@router.get("/threads/{thread_id}")
def get_thread(thread_id: ThreadId, resolve: ResolverDep, session: SessionDep) -> ThreadResponse:
    return _thread(threads.get_thread(_ports(session), resolve, thread_id))


@router.post(
    "/threads/{thread_id}/comments", status_code=status.HTTP_201_CREATED, responses=RATE_LIMITED
)
def reply(
    thread_id: ThreadId,
    body: ReplyRequest,
    idempotency_key: IdempotencyKey,
    resolve: ResolverDep,
    session: SessionDep,
) -> ThreadResponse:
    """Reply at the end of the thread; returns the whole thread. Any member may. 409
    `THREAD_RESOLVED` until someone reopens it."""
    view = threads.reply(
        _ports(session),
        resolve,
        thread_id,
        idempotency_key=idempotency_key,
        body=body.body,
        now=utc_now(),
    )
    _commit(session)
    return _thread(view)


@router.patch("/comments/{comment_id}")
def edit_comment(
    comment_id: CommentId,
    body: EditCommentRequest,
    idempotency_key: IdempotencyKey,
    resolve: ResolverDep,
    session: SessionDep,
) -> ThreadResponse:
    """Change your own comment's text; it shows as edited. 403 for anyone else's; 409
    `COMMENT_CHANGED` with `details.current_revision` when `expected_revision` is stale."""
    view = threads.edit_comment(
        _ports(session),
        resolve,
        comment_id,
        idempotency_key=idempotency_key,
        body=body.body,
        expected_revision=body.expected_revision,
        now=utc_now(),
    )
    _commit(session)
    return _thread(view)


@router.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_comment(comment_id: CommentId, resolve: ResolverDep, session: SessionDep) -> None:
    """Delete your own comment (403 for anyone else's). Its text is gone for everyone; a deleted
    first comment stays as "Comment deleted" while replies follow it."""
    threads.delete_comment(_ports(session), resolve, comment_id, utc_now())
    _commit(session)


@router.post("/threads/{thread_id}/resolve")
def resolve_thread(
    thread_id: ThreadId,
    body: ThreadStateRequest,
    idempotency_key: IdempotencyKey,
    resolve: ResolverDep,
    session: SessionDep,
) -> ThreadResponse:
    """Mark the discussion resolved. Its author, an editor or an approver may. 409
    `THREAD_CHANGED` with `details.current_revision` when `expected_revision` is stale."""
    view = threads.resolve_thread(
        _ports(session),
        resolve,
        thread_id,
        idempotency_key=idempotency_key,
        expected_revision=body.expected_revision,
        now=utc_now(),
    )
    _commit(session)
    return _thread(view)


@router.post("/threads/{thread_id}/reopen")
def reopen_thread(
    thread_id: ThreadId,
    body: ThreadStateRequest,
    idempotency_key: IdempotencyKey,
    resolve: ResolverDep,
    session: SessionDep,
) -> ThreadResponse:
    """Reopen a resolved discussion. Any member may."""
    view = threads.reopen_thread(
        _ports(session),
        resolve,
        thread_id,
        idempotency_key=idempotency_key,
        expected_revision=body.expected_revision,
        now=utc_now(),
    )
    _commit(session)
    return _thread(view)


def _ports(session: Session) -> Ports:
    return Ports(
        threads=SqlThreadStore(session),
        comments=SqlCommentStore(session),
        backlog=BacklogItems(session),
        receipts=SqlReceiptStore(session),
        audit=audit_recorder(session),
    )


def _thread(view: ThreadView) -> ThreadResponse:
    thread, item = view.thread, view.item
    return ThreadResponse(
        id=thread.id,
        project_id=thread.project_id,
        item_id=None if thread.item_id is None else ItemId(thread.item_id),
        item=None
        if item is None
        else ThreadItemResponse(
            id=item.id, kind=item.kind, title=item.title, in_current_backlog=item.in_current_backlog
        ),
        status="resolved" if thread.resolved else "open",
        revision=thread.revision,
        created_by=thread.created_by,
        created_at=thread.created_at,
        last_activity_at=thread.last_activity_at,
        resolved_at=thread.resolved_at,
        resolved_by=thread.resolved_by,
        resolved_by_name=thread.resolved_by_name,
        comments=[
            CommentResponse(
                id=comment.id,
                author_id=comment.author_id,
                author_name=comment.author_name,
                body=None if comment.deleted else comment.body,
                deleted=comment.deleted,
                revision=comment.revision,
                backlog_version_id=None
                if comment.backlog_version_id is None
                else BacklogVersionId(comment.backlog_version_id),
                created_at=comment.created_at,
                edited_at=comment.edited_at,
            )
            for comment in view.comments
        ],
    )


def _commit(session: Session) -> None:
    try:
        session.commit()
    except IntegrityError as error:
        # A concurrent request with the same Idempotency-Key won the unique constraint.
        session.rollback()
        raise ConcurrentCommandError(
            "Another request with this Idempotency-Key finished first. Try again."
        ) from error
