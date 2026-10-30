"""Discussion threads on backlog items and the project's General discussion, through the API with
session sign-in as the seeded viewer, editor and approver. Drafts and comments are synthetic."""

import secrets
from collections.abc import Callable, Generator
from contextlib import contextmanager
from typing import Any
from uuid import UUID

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from scopesteps.api.seed import DEMO_PROJECT_ID, LOCAL_REVIEWER_ID, SEED_ACCOUNTS, seed
from scopesteps.audit.infrastructure.orm import AuditEventRecord
from scopesteps.backlog.client import (
    CandidateProposal,
    Evidence,
    ProposedCriterion,
    ProposedItem,
    save_candidate,
)
from scopesteps.backlog.infrastructure.orm import ItemRevisionRecord, VersionRecord
from scopesteps.change_control.infrastructure.orm import ApprovalRecord
from scopesteps.identity.infrastructure.passwords import Argon2PasswordHasher
from scopesteps.infrastructure.database import (
    create_database_engine,
    create_session_factory,
    utc_now,
)
from scopesteps.kernel.ids import new_id
from scopesteps.projects.client import ProjectId

ClientFactory = Callable[..., TestClient]
Json = dict[str, Any]

PROJECT = f"/api/v1/projects/{DEMO_PROJECT_ID}"
THREADS = f"{PROJECT}/threads"
VIEWER, EDITOR, APPROVER = SEED_ACCOUNTS
BRIEF = b"# Room booking\n\nStudents book study rooms one slot at a time."
WEAK_HASHER = Argon2PasswordHasher(PasswordHasher(time_cost=1, memory_cost=8, parallelism=1))
HALLWAY_IDEA = "What if bookings could repeat weekly? Sam mentioned it in the corridor."


@contextmanager
def _session(database_url: str) -> Generator[Session]:
    engine = create_database_engine(database_url)
    with create_session_factory(engine)() as session:
        yield session
        session.commit()
    engine.dispose()


class Team:
    """The demo project's viewer, editor and approver, each signed in in their own browser, with
    a draft backlog of one epic and one story."""

    def __init__(self, make_client: ClientFactory, database_url: str, password: str) -> None:
        self.make_client = make_client
        self.database_url = database_url
        self.password = password
        self.browsers: dict[str, TestClient] = {}
        self.keys = 0

    def as_(self, email: str) -> TestClient:
        if email not in self.browsers:
            client = self.make_client(self.database_url, auth_mode="session")
            response = client.post(
                "/api/v1/auth/sign-in", json={"email": email, "password": self.password}
            )
            assert response.status_code == 200, response.text
            self.browsers[email] = client
        return self.browsers[email]

    @property
    def viewer(self) -> TestClient:
        return self.as_(VIEWER.email)

    @property
    def editor(self) -> TestClient:
        return self.as_(EDITOR.email)

    @property
    def approver(self) -> TestClient:
        return self.as_(APPROVER.email)

    def key(self) -> dict[str, str]:
        self.keys += 1
        return {"Idempotency-Key": f"discussion-test-{self.keys:05d}"}

    def save_draft(self) -> Json:
        response = self.editor.post(
            f"{PROJECT}/sources",
            files={"brief": ("brief.md", BRIEF)},
            headers=self.key(),
        )
        assert response.status_code == 201, response.text
        brief = UUID(response.json()["source_versions"][0]["id"])
        blocks = self.editor.get(f"{PROJECT}/sources/{brief}/blocks").json()
        proposal = CandidateProposal(
            project_id=ProjectId(DEMO_PROJECT_ID),
            run_id=new_id(),
            created_by=LOCAL_REVIEWER_ID,
            source_version_ids=(brief,),
            items=(
                ProposedItem("E1", "epic", None, "Room booking", "Booking study rooms."),
                ProposedItem(
                    "S1",
                    "story",
                    "E1",
                    "Book a room",
                    "As a student, I want to book a room, so that I can study.",
                    criteria=(
                        ProposedCriterion(
                            "A student books one slot.",
                            proposed=False,
                            evidence=(Evidence(brief, UUID(blocks[1]["id"])),),
                        ),
                    ),
                ),
            ),
            decisions=(),
        )
        with _session(self.database_url) as session:
            version_id = save_candidate(session, proposal, utc_now())
        return self.editor.get(f"{PROJECT}/backlogs/{version_id}").json()

    def start(
        self, client: TestClient, body: str = "Should a booking repeat weekly?", **fields: Any
    ) -> Response:
        return client.post(THREADS, json={"body": body, **fields}, headers=self.key())

    def started(self, client: TestClient, **fields: Any) -> Json:
        response = self.start(client, **fields)
        assert response.status_code == 201, response.text
        thread: Json = response.json()
        return thread

    def reply(self, client: TestClient, thread: Json, body: str = "Agreed.") -> Response:
        return client.post(
            f"/api/v1/threads/{thread['id']}/comments", json={"body": body}, headers=self.key()
        )

    def resolve(self, client: TestClient, thread: Json, action: str = "resolve") -> Response:
        return client.post(
            f"/api/v1/threads/{thread['id']}/{action}",
            json={"expected_revision": thread["revision"]},
            headers=self.key(),
        )

    def events(self, *types: str) -> list[Json]:
        feed = self.approver.get(f"{PROJECT}/activity").json()["events"]
        return [e for e in feed if e["type"] in types]

    def count(self, table: Any) -> int:
        with _session(self.database_url) as session:
            return session.scalar(select(func.count()).select_from(table)) or 0


@pytest.fixture
def team(migrated_database_url: str, make_client: ClientFactory) -> Team:
    password = secrets.token_urlsafe(16)
    engine = create_database_engine(migrated_database_url)
    with create_session_factory(engine)() as session:
        seed(session, account_password=password, hasher=WEAK_HASHER)
    engine.dispose()
    return Team(make_client, migrated_database_url, password)


@pytest.fixture
def draft(team: Team) -> Json:
    return team.save_draft()


def _item(version: Json, kind: str) -> Json:
    return next(item for item in version["items"] if item["kind"] == kind)


def _error(response: Response, status: int, code: str) -> Json:
    assert response.status_code == status, response.text
    body: Json = response.json()
    assert body["code"] == code, body
    return body


@pytest.mark.parametrize("kind", ["story", "epic", None])
def test_a_member_starts_a_thread_on_a_story_an_epic_or_general_discussion(
    team: Team, draft: Json, kind: str | None
) -> None:
    item = None if kind is None else _item(draft, kind)

    thread = team.started(team.viewer, item_id=None if item is None else item["id"])

    assert thread["status"] == "open"
    assert thread["item_id"] == (None if item is None else item["id"])
    if item is None:
        assert thread["item"] is None
    else:
        assert thread["item"] == {
            "id": item["id"],
            "kind": kind,
            "title": item["title"],
            "in_current_backlog": True,
        }
    [first] = thread["comments"]
    assert first["author_name"] == VIEWER.display_name
    assert first["backlog_version_id"] == draft["id"]


def test_replies_list_oldest_first_with_the_version_current_when_written(
    team: Team, draft: Json
) -> None:
    thread = team.started(team.editor, item_id=_item(draft, "story")["id"])
    team.reply(team.approver, thread, "Only for staff.")

    response = team.reply(team.viewer, thread, "Students too, please.")

    assert response.status_code == 201, response.text
    comments = response.json()["comments"]
    assert [c["author_name"] for c in comments] == [
        EDITOR.display_name,
        APPROVER.display_name,
        VIEWER.display_name,
    ]
    assert [c["body"] for c in comments][1:] == ["Only for staff.", "Students too, please."]
    assert {c["backlog_version_id"] for c in comments} == {draft["id"]}
    assert team.viewer.get(f"/api/v1/threads/{thread['id']}").json() == response.json()


def test_a_thread_lists_newest_activity_first_and_filters_by_item_and_status(
    team: Team, draft: Json
) -> None:
    story = _item(draft, "story")
    on_story = team.started(team.editor, item_id=story["id"])
    general = team.started(team.editor)
    team.reply(team.viewer, on_story)
    resolved = team.resolve(team.editor, general).json()

    every = team.viewer.get(THREADS).json()["threads"]
    only_story = team.viewer.get(THREADS, params={"item_id": story["id"]}).json()["threads"]
    only_general = team.viewer.get(THREADS, params={"general": "true"}).json()["threads"]
    open_ = team.viewer.get(THREADS, params={"status": "open"}).json()["threads"]
    counts = team.viewer.get(f"{THREADS}/counts").json()

    assert [t["id"] for t in every] == [on_story["id"], general["id"]]
    assert [t["id"] for t in only_story] == [on_story["id"]]
    assert [t["id"] for t in only_general] == [general["id"]]
    assert [t["id"] for t in open_] == [on_story["id"]]
    assert resolved["status"] == "resolved"
    assert counts == {
        "items": [{"item_id": story["id"], "open_threads": 1}],
        "general_open_threads": 0,
    }


def test_threads_page_by_cursor(team: Team) -> None:
    for _ in range(3):
        team.started(team.editor)

    first = team.viewer.get(THREADS, params={"limit": 2}).json()
    second = team.viewer.get(THREADS, params={"limit": 2, "cursor": first["next_cursor"]}).json()

    assert len(first["threads"]) == 2
    assert len(second["threads"]) == 1
    assert second["next_cursor"] is None
    _error(team.viewer.get(THREADS, params={"cursor": "nonsense"}), 422, "INVALID_CURSOR")


def test_an_author_edits_their_comment_and_it_shows_as_edited(team: Team) -> None:
    thread = team.started(team.viewer)
    comment = thread["comments"][0]

    response = team.viewer.patch(
        f"/api/v1/comments/{comment['id']}",
        json={"body": "Should bookings repeat every week?", "expected_revision": 1},
        headers=team.key(),
    )

    assert response.status_code == 200, response.text
    edited = response.json()["comments"][0]
    assert edited["body"] == "Should bookings repeat every week?"
    assert edited["edited_at"] is not None
    assert edited["revision"] == 2
    stale = team.viewer.patch(
        f"/api/v1/comments/{comment['id']}",
        json={"body": "Again", "expected_revision": 1},
        headers=team.key(),
    )
    assert _error(stale, 409, "COMMENT_CHANGED")["details"]["current_revision"] == 2


@pytest.mark.parametrize("who", [EDITOR, APPROVER])
def test_nobody_but_the_author_edits_or_deletes_a_comment(team: Team, who: Any) -> None:
    thread = team.started(team.viewer)
    comment = thread["comments"][0]
    other = team.as_(who.email)

    edit = other.patch(
        f"/api/v1/comments/{comment['id']}",
        json={"body": "Changed", "expected_revision": 1},
        headers=team.key(),
    )
    delete = other.delete(f"/api/v1/comments/{comment['id']}")

    _error(edit, 403, "PERMISSION_DENIED")
    _error(delete, 403, "PERMISSION_DENIED")
    assert team.viewer.get(f"/api/v1/threads/{thread['id']}").json()["comments"][0]["body"] == (
        "Should a booking repeat weekly?"
    )


def test_a_deleted_comment_with_replies_leaves_a_placeholder(team: Team) -> None:
    thread = team.started(team.viewer)
    team.reply(team.editor, thread, "Worth asking the sponsor.")

    response = team.viewer.delete(f"/api/v1/comments/{thread['comments'][0]['id']}")

    assert response.status_code == 204, response.text
    first, reply = team.editor.get(f"/api/v1/threads/{thread['id']}").json()["comments"]
    assert first["deleted"] is True
    assert first["body"] is None
    assert first["author_name"] == VIEWER.display_name
    assert reply["body"] == "Worth asking the sponsor."


def test_a_deleted_reply_disappears_and_a_thread_with_nothing_left_is_gone(team: Team) -> None:
    thread = team.started(team.viewer)
    reply = team.reply(team.editor, thread).json()["comments"][1]

    assert team.editor.delete(f"/api/v1/comments/{reply['id']}").status_code == 204
    assert len(team.viewer.get(f"/api/v1/threads/{thread['id']}").json()["comments"]) == 1
    assert team.viewer.delete(f"/api/v1/comments/{thread['comments'][0]['id']}").status_code == 204

    _error(team.viewer.get(f"/api/v1/threads/{thread['id']}"), 404, "NOT_FOUND")
    assert team.viewer.get(THREADS).json()["threads"] == []


@pytest.mark.parametrize("who", [VIEWER, EDITOR, APPROVER])
def test_the_author_an_editor_or_an_approver_resolves_and_anyone_reopens(
    team: Team, who: Any
) -> None:
    thread = team.started(team.viewer)

    resolved = team.resolve(team.as_(who.email), thread)

    assert resolved.status_code == 200, resolved.text
    body = resolved.json()
    assert body["status"] == "resolved"
    assert body["resolved_by_name"] == who.display_name
    reopened = team.resolve(team.viewer, body, "reopen")
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["status"] == "open"


def test_a_viewer_cannot_resolve_someone_elses_thread(team: Team) -> None:
    thread = team.started(team.editor)

    _error(team.resolve(team.viewer, thread), 403, "PERMISSION_DENIED")


def test_a_stale_revision_cannot_resolve_or_reopen(team: Team) -> None:
    thread = team.started(team.editor)
    team.resolve(team.approver, thread)

    stale = team.resolve(team.editor, thread)

    assert _error(stale, 409, "THREAD_CHANGED")["details"]["current_revision"] == 2


def test_a_resolved_thread_takes_no_reply_until_reopened(team: Team) -> None:
    thread = team.started(team.editor)
    resolved = team.resolve(team.editor, thread).json()

    _error(team.reply(team.viewer, thread), 409, "THREAD_RESOLVED")
    team.resolve(team.viewer, resolved, "reopen")
    assert team.reply(team.viewer, thread).status_code == 201


def test_non_members_get_404_on_every_endpoint(team: Team) -> None:
    thread = team.started(team.editor)
    comment = thread["comments"][0]
    other = team.approver.post("/api/v1/projects", json={"name": "Other"}, headers=team.key())
    their_threads = f"/api/v1/projects/{other.json()['id']}/threads"
    team.approver.post(their_threads, json={"body": "Ours only"}, headers=team.key())
    their_thread = team.approver.get(their_threads).json()["threads"][0]
    outsider = team.editor
    revision = {"expected_revision": their_thread["revision"]}

    responses = [
        outsider.get(their_threads),
        outsider.get(f"{their_threads}/counts"),
        outsider.post(their_threads, json={"body": "Hi"}, headers=team.key()),
        outsider.get(f"/api/v1/threads/{their_thread['id']}"),
        outsider.post(
            f"/api/v1/threads/{their_thread['id']}/comments",
            json={"body": "Hi"},
            headers=team.key(),
        ),
        outsider.post(
            f"/api/v1/threads/{their_thread['id']}/resolve", json=revision, headers=team.key()
        ),
        outsider.post(
            f"/api/v1/threads/{their_thread['id']}/reopen", json=revision, headers=team.key()
        ),
        outsider.patch(
            f"/api/v1/comments/{their_thread['comments'][0]['id']}",
            json={"body": "Hi", "expected_revision": 1},
            headers=team.key(),
        ),
        outsider.delete(f"/api/v1/comments/{their_thread['comments'][0]['id']}"),
    ]

    assert [r.status_code for r in responses] == [404] * len(responses)
    assert comment["body"]  # the outsider's own project still works for them


@pytest.mark.parametrize(
    ("body", "code"),
    [("", "COMMENT_EMPTY"), ("   \n\t ", "COMMENT_EMPTY"), ("x" * 5_001, "COMMENT_TOO_LONG")],
)
def test_empty_or_over_long_comments_are_refused(team: Team, body: str, code: str) -> None:
    thread = team.started(team.editor)

    _error(team.start(team.editor, body), 422, code)
    _error(team.reply(team.editor, thread, body), 422, code)


def test_a_comment_of_exactly_the_limit_is_accepted_and_kept_as_plain_text(team: Team) -> None:
    script = "<script>alert('x')</script>"
    body = script + "x" * (5_000 - len(script))

    thread = team.started(team.editor, body=f"  {body}  ")

    assert thread["comments"][0]["body"] == body


def test_a_thread_on_an_item_not_in_the_backlog_is_refused(team: Team) -> None:
    _error(team.start(team.editor, item_id=str(new_id())), 404, "ITEM_NOT_FOUND")


def test_the_thirty_first_comment_in_a_minute_is_refused(team: Team) -> None:
    thread = team.started(team.editor)
    for number in range(29):
        assert team.reply(team.editor, thread, f"Point {number}").status_code == 201

    response = team.reply(team.editor, thread, "One more")

    assert _error(response, 429, "RATE_LIMITED")["retryable"] is True
    assert team.reply(team.viewer, thread, "Someone else may still post").status_code == 201


def test_a_repeated_request_is_applied_once(team: Team) -> None:
    key = team.key()
    first = team.editor.post(THREADS, json={"body": "Once"}, headers=key)
    again = team.editor.post(THREADS, json={"body": "Once"}, headers=key)
    other = team.editor.post(THREADS, json={"body": "Different"}, headers=key)

    assert again.json()["id"] == first.json()["id"]
    _error(other, 409, "IDEMPOTENCY_KEY_REUSED")
    assert len(team.editor.get(THREADS).json()["threads"]) == 1
    assert len(team.events("thread.started")) == 1


def test_approving_the_draft_keeps_threads_on_their_items(team: Team, draft: Json) -> None:
    story = _item(draft, "story")
    thread = team.started(team.editor, item_id=story["id"])
    approved = team.approver.post(
        f"/api/v1/backlogs/{draft['id']}/approve",
        json={
            "expected_revision": draft["revision"],
            "content_hash": draft["content_hash"],
            "expected_baseline_id": None,
        },
        headers=team.key(),
    )
    assert approved.status_code == 200, approved.text

    listed = team.viewer.get(THREADS, params={"item_id": story["id"]}).json()["threads"]

    assert [t["id"] for t in listed] == [thread["id"]]
    assert listed[0]["item"]["in_current_backlog"] is True
    reply = team.reply(team.viewer, thread).json()["comments"][-1]
    assert reply["backlog_version_id"] == draft["id"]


def test_a_thread_on_an_item_no_longer_in_the_backlog_stays_readable(
    team: Team, draft: Json
) -> None:
    thread = team.started(team.editor, item_id=_item(draft, "story")["id"])
    team.save_draft()

    found = team.viewer.get(f"/api/v1/threads/{thread['id']}").json()

    assert found["item"]["title"] == "Book a room"
    assert found["item"]["in_current_backlog"] is False


def test_no_discussion_endpoint_changes_backlog_decision_or_approval_rows(
    team: Team, draft: Json
) -> None:
    tables = (VersionRecord, ItemRevisionRecord, ApprovalRecord)
    before = [team.count(table) for table in tables]
    version_before = team.editor.get(f"{PROJECT}/backlogs/{draft['id']}").json()

    thread = team.started(team.editor, item_id=_item(draft, "story")["id"])
    team.reply(team.approver, thread)
    team.resolve(team.approver, thread)
    team.viewer.delete(f"/api/v1/comments/{thread['comments'][0]['id']}")

    assert [team.count(table) for table in tables] == before
    assert team.editor.get(f"{PROJECT}/backlogs/{draft['id']}").json() == version_before


def test_thread_events_name_the_item_but_never_the_comment_text(team: Team, draft: Json) -> None:
    story = _item(draft, "story")
    thread = team.started(team.editor, item_id=story["id"], body=HALLWAY_IDEA)
    resolved = team.resolve(team.approver, thread).json()
    team.resolve(team.viewer, resolved, "reopen")
    general = team.started(team.viewer, body=HALLWAY_IDEA)

    events = team.events("thread.started", "thread.resolved", "thread.reopened")

    assert [e["summary"] for e in events] == [
        "Started a discussion on General discussion",
        "Reopened a discussion on story “Book a room”",
        "Resolved a discussion on story “Book a room”",
        "Started a discussion on story “Book a room”",
    ]
    assert {s["id"] for s in events[-1]["subjects"]} == {thread["id"], story["id"]}
    assert events[0]["subjects"] == [{"kind": "thread", "id": general["id"]}]
    with _session(team.database_url) as session:
        summaries = session.scalars(select(AuditEventRecord.summary)).all()
    assert not any("weekly" in summary or "corridor" in summary for summary in summaries)


def test_refused_actions_record_no_event(team: Team) -> None:
    thread = team.started(team.editor)
    before = len(team.events("thread.started", "thread.resolved", "thread.reopened"))

    team.start(team.editor, "")
    team.start(team.editor, item_id=str(new_id()))
    team.resolve(team.viewer, thread)
    team.resolve(team.editor, {**thread, "revision": 7})
    team.resolve(team.editor, thread, "reopen")  # already open: nothing to record

    assert len(team.events("thread.started", "thread.resolved", "thread.reopened")) == before


def test_people_who_leave_keep_their_name_on_what_they_wrote(team: Team) -> None:
    thread = team.started(team.viewer)
    left = team.viewer.delete(f"{PROJECT}/members/{VIEWER.id}")
    assert left.status_code == 204, left.text

    found = team.editor.get(f"/api/v1/threads/{thread['id']}").json()

    assert found["comments"][0]["author_name"] == VIEWER.display_name
    _error(team.viewer.get(f"/api/v1/threads/{thread['id']}"), 404, "NOT_FOUND")
