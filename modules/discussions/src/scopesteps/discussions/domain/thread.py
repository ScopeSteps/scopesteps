"""A discussion: a thread on one epic or story, or on the project's General discussion, made of a
first comment and its replies (ADR 0020).

A comment is never a decision. Nothing here changes the backlog, a scope decision or an approval,
and nothing here is sent to the agent.
"""

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Self
from uuid import UUID

from scopesteps.discussions.domain.ids import CommentId, ThreadId
from scopesteps.identity.client import UserId
from scopesteps.kernel.errors import ConflictError, InvalidInputError, NotFoundError
from scopesteps.projects.client import ProjectId

MAX_BODY_CHARS = 5_000


class CommentEmptyError(InvalidInputError):
    code = "COMMENT_EMPTY"


class CommentTooLongError(InvalidInputError):
    code = "COMMENT_TOO_LONG"


class ItemNotFoundError(NotFoundError):
    code = "ITEM_NOT_FOUND"


class ThreadChangedError(ConflictError):
    code = "THREAD_CHANGED"


class CommentChangedError(ConflictError):
    code = "COMMENT_CHANGED"


class ThreadResolvedError(ConflictError):
    code = "THREAD_RESOLVED"


class CommentDeletedError(ConflictError):
    code = "COMMENT_DELETED"


def comment_body(raw: str) -> str:
    """The text as stored: plain text, trimmed, never empty and at most MAX_BODY_CHARS. It is
    returned as written; the web app escapes it."""
    body = raw.strip()
    if not body:
        raise CommentEmptyError("Write something before posting", details={"field": "body"})
    if len(body) > MAX_BODY_CHARS:
        raise CommentTooLongError(
            f"A comment can be at most {MAX_BODY_CHARS:,} characters",
            details={"field": "body", "max_chars": MAX_BODY_CHARS},
        )
    return body


@dataclass(frozen=True)
class Comment:
    id: CommentId
    thread_id: ThreadId
    project_id: ProjectId
    author_id: UserId
    author_name: str
    """Copied when written, so the comment keeps its author's name after they leave."""
    body: str
    backlog_version_id: UUID | None
    """The backlog version in flight, or else the baseline, when it was written; None before any."""
    created_at: datetime
    revision: int = 1
    edited_at: datetime | None = None
    deleted_at: datetime | None = None

    @property
    def deleted(self) -> bool:
        return self.deleted_at is not None

    def edited(self, body: str, now: datetime) -> Self:
        if self.deleted:
            raise CommentDeletedError("This comment was deleted")
        return replace(self, body=body, edited_at=now, revision=self.revision + 1)


@dataclass(frozen=True)
class Thread:
    id: ThreadId
    project_id: ProjectId
    item_id: UUID | None
    """The epic or story, by the id `backlog` keeps across versions; None for the project's
    General discussion."""
    created_by: UserId
    created_at: datetime
    last_activity_at: datetime
    """When the newest comment was posted; the order threads are listed in."""
    open_comments: int
    """Comments not deleted. A thread with none left is gone from every list."""
    revision: int = 1
    resolved_at: datetime | None = None
    resolved_by: UserId | None = None
    resolved_by_name: str | None = None

    @property
    def resolved(self) -> bool:
        return self.resolved_at is not None

    def resolve(self, by: UserId, name: str, now: datetime) -> Self:
        return replace(
            self,
            resolved_at=now,
            resolved_by=by,
            resolved_by_name=name,
            revision=self.revision + 1,
        )

    def reopen(self) -> Self:
        return replace(
            self,
            resolved_at=None,
            resolved_by=None,
            resolved_by_name=None,
            revision=self.revision + 1,
        )


def visible_comments(comments: list[Comment]) -> list[Comment]:
    """A thread's comments oldest first, as everyone sees them. A deleted reply is left out; a
    deleted first comment stays as a placeholder while replies follow it, so they still read
    as answers to something."""
    return [
        comment
        for position, comment in enumerate(comments)
        if not comment.deleted
        or (position == 0 and any(not reply.deleted for reply in comments[1:]))
    ]
