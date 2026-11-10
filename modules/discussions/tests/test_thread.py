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
    participants,
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


def _by(author: UserId, body: str, *, name: str = "Sample Editor") -> Comment:
    return replace(_comment(body), author_id=author, author_name=name)


def test_participants_follow_the_order_people_appear_then_other_followers_by_name() -> None:
    ana, ben, cai, dee, eve = (UserId(uuid4()) for _ in range(5))
    comments = [_by(ana, f"Over to <@{ben}>"), _by(cai, "Agreed")]
    names = {ana: "Ana", ben: "Ben", cai: "Cai", dee: "Dee", eve: "Eve"}

    found = participants(comments, {eve, dee, ana}, members={ana, ben, cai, dee, eve}, names=names)

    assert [p.display_name for p in found] == ["Ana", "Ben", "Cai", "Dee", "Eve"]
    assert [(p.wrote, p.mentioned, p.following) for p in found] == [
        (True, False, True),
        (False, True, False),
        (True, False, False),
        (False, False, True),
        (False, False, True),
    ]


def test_people_who_left_stay_marked_with_their_name_and_no_longer_follow() -> None:
    gone, member = UserId(uuid4()), UserId(uuid4())
    comments = [_by(gone, "Before I go", name="Former Editor"), _by(member, "Thanks")]

    found = participants(comments, {gone, member}, members={member}, names={member: "Member"})

    assert [(p.display_name, p.left_project, p.following) for p in found] == [
        ("Former Editor", True, False),
        ("Member", False, True),
    ]


def test_a_follower_who_left_and_never_wrote_is_not_a_participant() -> None:
    gone, member = UserId(uuid4()), UserId(uuid4())

    found = participants([_by(member, "Hello")], {gone}, members={member}, names={})

    assert [p.user_id for p in found] == [member]


def test_a_deleted_comment_counts_for_nobody() -> None:
    author, named = UserId(uuid4()), UserId(uuid4())
    deleted = replace(_by(author, f"Ask <@{named}>"), deleted_at=NOW)

    assert participants([deleted], set(), members={author, named}, names={}) == ()
