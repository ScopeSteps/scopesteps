from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from scopesteps.discussions.domain.ids import CommentId, ThreadId
from scopesteps.discussions.domain.thread import (
    MAX_BODY_CHARS,
    Comment,
    CommentDeletedError,
    CommentEmptyError,
    CommentTooLongError,
    comment_body,
    visible_comments,
)
from scopesteps.identity.client import UserId
from scopesteps.projects.client import ProjectId

NOW = datetime(2026, 10, 29, 9, 0, tzinfo=UTC)


def _comment(body: str = "A thought", *, deleted: bool = False) -> Comment:
    return Comment(
        id=CommentId(uuid4()),
        thread_id=ThreadId(uuid4()),
        project_id=ProjectId(uuid4()),
        author_id=UserId(uuid4()),
        author_name="Sample Editor",
        body="" if deleted else body,
        backlog_version_id=None,
        created_at=NOW,
        deleted_at=NOW if deleted else None,
    )


def test_a_body_is_trimmed_and_kept_as_written() -> None:
    assert comment_body("  <b>Bold</b> idea\n") == "<b>Bold</b> idea"


@pytest.mark.parametrize(
    ("raw", "error"),
    [("", CommentEmptyError), (" \n", CommentEmptyError), ("x" * 5_001, CommentTooLongError)],
)
def test_an_empty_or_over_long_body_is_refused(raw: str, error: type[Exception]) -> None:
    with pytest.raises(error):
        comment_body(raw)


def test_the_limit_counts_after_trimming() -> None:
    assert len(comment_body(" " + "x" * MAX_BODY_CHARS + " ")) == MAX_BODY_CHARS


def test_an_edit_moves_the_revision_and_marks_it_edited() -> None:
    edited = _comment().edited("Better thought", NOW)

    assert (edited.body, edited.revision, edited.edited_at) == ("Better thought", 2, NOW)


def test_a_deleted_comment_cannot_be_edited() -> None:
    with pytest.raises(CommentDeletedError):
        _comment(deleted=True).edited("Back again", NOW)


def test_a_deleted_first_comment_stays_only_while_replies_follow() -> None:
    first, reply = _comment(deleted=True), _comment("Reply")

    assert visible_comments([first, reply]) == [first, reply]
    assert visible_comments([first, replace(reply, deleted_at=NOW)]) == []


def test_a_deleted_reply_is_left_out() -> None:
    first, reply, last = _comment(), _comment(deleted=True), _comment("Last")

    assert visible_comments([first, reply, last]) == [first, last]
