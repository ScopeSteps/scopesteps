"""A discussion: a thread on one epic or story, or on the project's General discussion, made of a
first comment and its replies (ADR 0020).

A comment is never a decision. Nothing here changes the backlog, a scope decision or an approval,
and nothing here reaches the agent unless a person quotes it into a change request.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Self
from uuid import UUID

from scopesteps.discussions.domain.ids import CommentId, ThreadId
from scopesteps.identity.client import UserId
from scopesteps.kernel.errors import ConflictError, InvalidInputError, NotFoundError
from scopesteps.projects.client import ProjectId

MAX_BODY_CHARS = 5_000

# How a body stores a mention: the id, so a renamed person keeps being named correctly.
_MENTION = re.compile(
    r"<@([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})>", re.IGNORECASE
)
FORMER_MEMBER = "A former member"
_SHORTENED_NOTE = "(Earlier comments were left out to fit.)"
_PARAGRAPH = "\n\n"


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


class MentionNotMemberError(InvalidInputError):
    code = "MENTION_NOT_MEMBER"


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


def mentioned_users(body: str) -> tuple[UserId, ...]:
    """Who a body mentions, once each, in the order it names them."""
    return tuple(dict.fromkeys(UserId(UUID(match)) for match in _MENTION.findall(body)))


def with_names(body: str, names: Mapping[UserId, str]) -> str:
    """The body as a reader sees it, each mention replaced by the person's name."""
    return _MENTION.sub(lambda match: f"@{names.get(UserId(UUID(match[1])), FORMER_MEMBER)}", body)


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


def quote_comments(
    comments: Sequence[Comment], names: Mapping[UserId, str], *, max_chars: int
) -> tuple[str, bool]:
    """The comments as a change request quotes them, and whether any had to go.

    Each comment is one paragraph, so the agent can cite it on its own: "<name>, <date>: <text>".
    Text is flattened to what a change request accepts. The newest comments are kept: the oldest
    go first and a note says so, and a newest comment too long by itself is cut.
    """
    lines = [_quoted_line(comment, names) for comment in comments if not comment.deleted]
    budget = max_chars - len(_SHORTENED_NOTE) - len(_PARAGRAPH)
    kept: list[str] = []
    for line in reversed(lines):
        cost = len(line) + len(_PARAGRAPH)
        if cost > budget:
            break
        kept.insert(0, line)
        budget -= cost
    if len(kept) == len(lines):
        return _PARAGRAPH.join(lines), False
    if not kept:
        kept = [lines[-1][: budget - 1].rstrip() + "…"]
    return _PARAGRAPH.join([_SHORTENED_NOTE, *kept]), True


def _quoted_line(comment: Comment, names: Mapping[UserId, str]) -> str:
    text = " ".join(with_names(comment.body, names).split())
    # A change request refuses control and invisible characters, which a comment may hold.
    printable = "".join(char for char in text if char.isprintable())
    return f"{comment.author_name}, {comment.created_at:%Y-%m-%d}: {printable}"
