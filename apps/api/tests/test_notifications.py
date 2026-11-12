"""Mentions, following, notifications and their emails, through the API with session sign-in as
the seeded viewer, editor and approver. Comments are synthetic; the email service is a recording
fake and the background job runs when a test ticks it, at the time the test chooses."""

import secrets
from collections.abc import Callable
from datetime import timedelta
from typing import Any, cast
from uuid import UUID

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from httpx2 import Response

from scopesteps.api.notification_job import NotificationJob
from scopesteps.api.seed import DEMO_PROJECT_ID, SEED_ACCOUNTS, seed
from scopesteps.identity.infrastructure.email import RecordingEmailSender
from scopesteps.identity.infrastructure.passwords import Argon2PasswordHasher
from scopesteps.infrastructure.database import (
    create_database_engine,
    create_session_factory,
    utc_now,
)
from scopesteps.kernel.ids import new_id
from scopesteps.notifications.infrastructure.orm import NotificationRecord

ClientFactory = Callable[..., TestClient]
Json = dict[str, Any]

PROJECT = f"/api/v1/projects/{DEMO_PROJECT_ID}"
THREADS = f"{PROJECT}/threads"
BASE_URL = "https://app.scopesteps.test"
VIEWER, EDITOR, APPROVER = SEED_ACCOUNTS
WEAK_HASHER = Argon2PasswordHasher(PasswordHasher(time_cost=1, memory_cost=8, parallelism=1))
PRIVATE_WORDS = "the caretaker's confidential budget"


def mention(user: Any) -> str:
    return f"<@{user.id}>"


class Team:
    """The demo project's viewer, editor and approver, each signed in in their own browser."""

    def __init__(self, make_client: ClientFactory, database_url: str, password: str) -> None:
        self.make_client = make_client
        self.database_url = database_url
        self.password = password
        self.mail = RecordingEmailSender()
        self.browsers: dict[str, TestClient] = {}
        self.keys = 0

    def as_(self, user: Any) -> TestClient:
        if user.email not in self.browsers:
            client = self.make_client(self.database_url, auth_mode="session", app_base_url=BASE_URL)
            client.app.state.email_sender = self.mail  # type: ignore[attr-defined]
            response = client.post(
                "/api/v1/auth/sign-in", json={"email": user.email, "password": self.password}
            )
            assert response.status_code == 200, response.text
            self.browsers[user.email] = client
        return self.browsers[user.email]

    def key(self) -> dict[str, str]:
        self.keys += 1
        return {"Idempotency-Key": f"notification-test-{self.keys:05d}"}

    def start(self, user: Any, body: str = "Should a booking repeat weekly?") -> Json:
        response = self.as_(user).post(THREADS, json={"body": body}, headers=self.key())
        assert response.status_code == 201, response.text
        return response.json()

    def reply(self, user: Any, thread: Json, body: str = "Agreed.") -> Json:
        response = self.as_(user).post(
            f"/api/v1/threads/{thread['id']}/comments", json={"body": body}, headers=self.key()
        )
        assert response.status_code == 201, response.text
        return response.json()

    def edit(self, user: Any, comment: Json, body: str) -> Response:
        return self.as_(user).patch(
            f"/api/v1/comments/{comment['id']}",
            json={"body": body, "expected_revision": comment["revision"]},
            headers=self.key(),
        )

    def follow(self, user: Any, thread: Json, *, following: bool) -> Json:
        response = self.as_(user).put(
            f"/api/v1/threads/{thread['id']}/follow", json={"following": following}
        )
        assert response.status_code == 200, response.text
        return response.json()

    def inbox(self, user: Any, **params: Any) -> list[Json]:
        response = self.as_(user).get("/api/v1/me/notifications", params=params)
        assert response.status_code == 200, response.text
        return response.json()["notifications"]

    def kinds(self, user: Any) -> list[str]:
        return [n["kind"] for n in self.inbox(user)]

    def unread(self, user: Any) -> int:
        return self.as_(user).get("/api/v1/me/notifications/unread-count").json()["unread"]

    def settings(self, user: Any, *, mention: bool, reply: bool) -> None:
        response = self.as_(user).put(
            "/api/v1/me/notification-settings",
            json={"email_on_mention": mention, "email_on_reply": reply},
        )
        assert response.status_code == 200, response.text

    def tick(self, minutes: int = 0) -> int:
        client = self.as_(APPROVER)
        job = cast(NotificationJob, client.app.state.notification_job)  # type: ignore[attr-defined]
        return job.tick(utc_now() + timedelta(minutes=minutes))

    def remove(self, user: Any) -> None:
        response = self.as_(APPROVER).delete(f"{PROJECT}/members/{user.id}")
        assert response.status_code == 204, response.text


@pytest.fixture
def team(migrated_database_url: str, make_client: ClientFactory) -> Team:
    password = secrets.token_urlsafe(16)
    engine = create_database_engine(migrated_database_url)
    with create_session_factory(engine)() as session:
        seed(session, account_password=password, hasher=WEAK_HASHER)
    engine.dispose()
    return Team(make_client, migrated_database_url, password)


def test_the_picker_finds_members_by_name_without_their_emails(team: Team) -> None:
    response = team.as_(VIEWER).get(f"{PROJECT}/members/search", params={"q": "sample e"})

    assert response.status_code == 200, response.text
    assert response.json() == {
        "members": [
            {"user_id": str(EDITOR.id), "display_name": EDITOR.display_name, "role": "editor"}
        ]
    }


def test_someone_outside_the_project_cannot_search_its_members(team: Team) -> None:
    team.as_(VIEWER)
    team.remove(VIEWER)

    response = team.as_(VIEWER).get(f"{PROJECT}/members/search", params={"q": "sample"})

    assert response.status_code == 404


def test_a_mention_is_stored_by_id_shown_by_name_and_notifies_the_person(team: Team) -> None:
    thread = team.start(EDITOR, f"What do you think, {mention(VIEWER)}?")

    (comment,) = thread["comments"]
    assert comment["body"] == f"What do you think, {mention(VIEWER)}?"
    assert comment["mentions"] == [{"user_id": str(VIEWER.id), "display_name": VIEWER.display_name}]
    (notification,) = team.inbox(VIEWER)
    assert notification["kind"] == "mentioned"
    assert notification["actor_name"] == EDITOR.display_name
    assert notification["project_name"]
    assert notification["item"] is None, "General discussion"
    assert notification["thread_id"] == thread["id"]
    assert notification["comment_id"] == comment["id"]
    assert team.unread(VIEWER) == 1


def test_renaming_someone_updates_their_old_mentions(team: Team) -> None:
    thread = team.start(EDITOR, f"Over to {mention(VIEWER)}")
    profile = team.as_(VIEWER).get("/api/v1/me").json()

    team.as_(VIEWER).patch(
        "/api/v1/me",
        json={
            "display_name": "Renamed Viewer",
            "job_title": "",
            "about": "",
            "expected_revision": profile["revision"],
        },
    )

    read = team.as_(EDITOR).get(f"/api/v1/threads/{thread['id']}").json()
    assert read["comments"][0]["mentions"][0]["display_name"] == "Renamed Viewer"


@pytest.mark.parametrize("stranger", [new_id(), "former"])
def test_only_current_members_can_be_mentioned(team: Team, stranger: Any) -> None:
    team.as_(VIEWER)
    if stranger == "former":
        team.remove(VIEWER)
        stranger = VIEWER.id
    thread = team.start(EDITOR)
    body = {"body": f"Hello <@{stranger}>"}

    started = team.as_(EDITOR).post(THREADS, json=body, headers=team.key())
    replied = team.as_(EDITOR).post(
        f"/api/v1/threads/{thread['id']}/comments", json=body, headers=team.key()
    )
    edited = team.edit(EDITOR, thread["comments"][0], body["body"])

    for response in (started, replied, edited):
        assert response.status_code == 422, response.text
        assert response.json()["code"] == "MENTION_NOT_MEMBER"


def test_editing_a_comment_may_keep_naming_someone_who_left(team: Team) -> None:
    thread = team.start(EDITOR, f"Ask {mention(VIEWER)}")
    team.remove(VIEWER)

    response = team.edit(EDITOR, thread["comments"][0], f"Ask {mention(VIEWER)} about it")

    assert response.status_code == 200, response.text


def test_text_that_only_looks_like_a_mention_is_left_alone(team: Team) -> None:
    thread = team.start(EDITOR, "Use <@not-a-person> as the placeholder")

    assert thread["comments"][0]["mentions"] == []


def test_people_in_a_thread_hear_of_replies_and_the_author_never_does(team: Team) -> None:
    thread = team.start(EDITOR)
    team.reply(APPROVER, thread)
    team.reply(VIEWER, thread)

    team.reply(EDITOR, thread)

    assert team.kinds(EDITOR) == ["replied", "replied"]
    assert team.kinds(APPROVER) == ["replied", "replied"]
    assert team.kinds(VIEWER) == ["replied"]


def test_being_mentioned_follows_the_thread(team: Team) -> None:
    thread = team.start(EDITOR, f"Over to {mention(VIEWER)}")

    assert team.as_(VIEWER).get(f"/api/v1/threads/{thread['id']}").json()["following"] is True
    team.reply(APPROVER, thread)

    assert team.kinds(VIEWER) == ["replied", "mentioned"]


def test_a_mentioned_follower_gets_one_notification_for_the_comment(team: Team) -> None:
    thread = team.start(EDITOR)

    team.reply(APPROVER, thread, f"Right, {mention(EDITOR)}?")

    assert team.kinds(EDITOR) == ["mentioned"]


def test_mentioning_yourself_notifies_nobody(team: Team) -> None:
    team.start(EDITOR, f"Note to {mention(EDITOR)}")

    assert team.inbox(EDITOR) == []


def test_unfollowing_stops_replies_until_followed_again_but_not_mentions(team: Team) -> None:
    thread = team.start(EDITOR)
    assert team.follow(EDITOR, thread, following=False)["following"] is False

    team.reply(APPROVER, thread)
    assert team.inbox(EDITOR) == []

    team.reply(EDITOR, thread, "Still here, but do not tell me.")
    team.reply(APPROVER, thread)
    assert team.inbox(EDITOR) == [], "commenting does not undo an unfollow"

    team.reply(APPROVER, thread, f"This one is for you, {mention(EDITOR)}")
    assert team.kinds(EDITOR) == ["mentioned"]

    team.reply(APPROVER, thread)
    assert team.kinds(EDITOR) == ["mentioned"], "a mention does not undo an unfollow either"

    assert team.follow(EDITOR, thread, following=True)["following"] is True
    team.reply(APPROVER, thread)
    assert team.kinds(EDITOR) == ["replied", "mentioned"]


def test_anyone_in_the_project_may_follow_a_thread_they_never_wrote_in(team: Team) -> None:
    thread = team.start(EDITOR)
    team.follow(VIEWER, thread, following=True)

    team.reply(EDITOR, thread)

    assert team.kinds(VIEWER) == ["replied"]


def test_someone_outside_the_project_cannot_follow_its_threads(team: Team) -> None:
    thread = team.start(EDITOR)
    team.as_(VIEWER)
    team.remove(VIEWER)

    response = team.as_(VIEWER).put(
        f"/api/v1/threads/{thread['id']}/follow", json={"following": True}
    )

    assert response.status_code == 404


def test_an_edit_notifies_only_people_it_newly_mentions(team: Team) -> None:
    thread = team.start(EDITOR, f"Over to {mention(VIEWER)}")
    team.reply(APPROVER, thread)
    first = team.as_(EDITOR).get(f"/api/v1/threads/{thread['id']}").json()["comments"][0]

    edited = team.edit(EDITOR, first, f"Over to {mention(VIEWER)} and {mention(APPROVER)}")

    assert edited.status_code == 200, edited.text
    assert team.kinds(VIEWER).count("mentioned") == 1
    assert team.kinds(APPROVER) == ["mentioned"]


def test_taking_a_mention_out_and_back_does_not_notify_twice(team: Team) -> None:
    thread = team.start(EDITOR, f"Over to {mention(VIEWER)}")
    comment = thread["comments"][0]

    without = team.edit(EDITOR, comment, "Over to nobody").json()["comments"][0]
    team.edit(EDITOR, without, f"Over to {mention(VIEWER)}")

    assert team.kinds(VIEWER) == ["mentioned"]


def test_a_retried_comment_notifies_once(team: Team) -> None:
    key = team.key()
    body = {"body": f"Over to {mention(VIEWER)}"}

    for _ in range(2):
        team.as_(EDITOR).post(THREADS, json=body, headers=key)

    assert team.kinds(VIEWER) == ["mentioned"]


def test_deleting_a_comment_withdraws_what_it_caused(team: Team) -> None:
    thread = team.start(EDITOR)
    comment = team.reply(APPROVER, thread, f"Over to {mention(VIEWER)}")["comments"][-1]

    team.as_(APPROVER).delete(f"/api/v1/comments/{comment['id']}")

    assert team.inbox(VIEWER) == []
    assert team.tick() == 0


def test_reading_counts_down_and_read_all_clears(team: Team) -> None:
    for number in range(3):
        team.start(EDITOR, f"Number {number}, {mention(VIEWER)}")
    newest, *_ = team.inbox(VIEWER)

    read = team.as_(VIEWER).post(f"/api/v1/me/notifications/{newest['id']}/read")

    assert read.status_code == 204, read.text
    assert team.unread(VIEWER) == 2
    assert len(team.inbox(VIEWER, unread=True)) == 2
    assert team.inbox(VIEWER)[0]["read_at"] is not None

    cleared = team.as_(VIEWER).post("/api/v1/me/notifications/read-all")

    assert cleared.status_code == 204, cleared.text
    assert team.unread(VIEWER) == 0


def test_reading_someone_elses_notification_is_not_found(team: Team) -> None:
    team.start(EDITOR, f"Over to {mention(VIEWER)}")
    (notification,) = team.inbox(VIEWER)

    response = team.as_(APPROVER).post(f"/api/v1/me/notifications/{notification['id']}/read")

    assert response.status_code == 404
    assert team.unread(VIEWER) == 1


def test_the_list_is_newest_first_a_page_at_a_time(team: Team) -> None:
    for number in range(3):
        team.start(EDITOR, f"Number {number}, {mention(VIEWER)}")

    first = team.as_(VIEWER).get("/api/v1/me/notifications", params={"limit": 2}).json()
    second = team.as_(VIEWER).get(
        "/api/v1/me/notifications", params={"limit": 2, "cursor": first["next_cursor"]}
    )

    assert len(first["notifications"]) == 2
    assert first["next_cursor"] is not None
    assert len(second.json()["notifications"]) == 1
    assert second.json()["next_cursor"] is None
    created = [n["created_at"] for n in first["notifications"]]
    assert created == sorted(created, reverse=True)


def test_a_bad_cursor_is_refused(team: Team) -> None:
    response = team.as_(VIEWER).get("/api/v1/me/notifications", params={"cursor": "nonsense"})

    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_CURSOR"


def test_someone_removed_from_a_project_loses_its_notifications_and_emails(team: Team) -> None:
    thread = team.start(EDITOR, f"Over to {mention(VIEWER)}")
    team.reply(VIEWER, thread)
    (notification, *_) = team.inbox(VIEWER) or [None]
    assert notification is not None

    team.remove(VIEWER)
    team.reply(EDITOR, thread)

    assert team.inbox(VIEWER) == []
    assert team.unread(VIEWER) == 0
    response = team.as_(VIEWER).post(f"/api/v1/me/notifications/{notification['id']}/read")
    assert response.status_code == 404
    team.tick()
    assert VIEWER.email not in [message.to for message in team.mail.sent]


def test_replies_after_someone_left_do_not_wait_for_them_to_return(team: Team) -> None:
    thread = team.start(EDITOR)
    team.reply(VIEWER, thread)
    team.remove(VIEWER)

    team.reply(EDITOR, thread)

    engine = create_database_engine(team.database_url)
    with create_session_factory(engine)() as session:
        rows = session.query(NotificationRecord).filter_by(user_id=VIEWER.id).count()
    engine.dispose()
    assert rows == 0


def test_a_mention_emails_by_default_and_a_reply_does_not(team: Team) -> None:
    thread = team.start(EDITOR, f"Over to {mention(VIEWER)}")
    team.reply(APPROVER, thread, "A reply.")

    assert team.tick() == 1

    (message,) = team.mail.sent
    assert message.to == VIEWER.email
    assert EDITOR.display_name in message.subject
    assert "mentioned you" in message.subject
    assert team.as_(VIEWER).get("/api/v1/me/notification-settings").json() == {
        "email_on_mention": True,
        "email_on_reply": False,
        "email_on_jira_failure": True,
    }


def test_settings_switch_both_kinds(team: Team) -> None:
    team.settings(VIEWER, mention=False, reply=True)
    thread = team.start(EDITOR, f"Over to {mention(VIEWER)}")
    assert team.tick() == 0

    team.reply(APPROVER, thread, "A reply.")

    assert team.tick(16) == 1
    (message,) = team.mail.sent
    assert message.to == VIEWER.email
    assert "replied on" in message.subject


def test_turning_email_off_stops_what_is_waiting(team: Team) -> None:
    team.start(EDITOR, f"Over to {mention(VIEWER)}")
    team.settings(VIEWER, mention=False, reply=False)

    assert team.tick() == 0
    team.settings(VIEWER, mention=True, reply=False)
    assert team.tick(16) == 0, "a decision is final: nothing old comes back"


def test_three_mentions_in_fifteen_minutes_send_one_email_and_then_one_batch(team: Team) -> None:
    thread = team.start(EDITOR, f"One, {mention(VIEWER)}")
    assert team.tick() == 1

    team.reply(EDITOR, thread, f"Two, {mention(VIEWER)}")
    team.reply(APPROVER, thread, f"Three, {mention(VIEWER)}")

    assert team.tick(14) == 0
    assert len(team.mail.sent) == 1
    assert team.tick(16) == 1
    assert len(team.mail.sent) == 2
    assert "2 new comments" in team.mail.sent[1].subject


def test_one_email_covers_mentions_that_arrive_before_the_job_runs(team: Team) -> None:
    thread = team.start(EDITOR, f"One, {mention(VIEWER)}")
    team.reply(EDITOR, thread, f"Two, {mention(VIEWER)}")
    team.reply(APPROVER, thread, f"Three, {mention(VIEWER)}")

    assert team.tick() == 1
    assert team.tick(30) == 0, "all three went out together"


def test_each_thread_has_its_own_window(team: Team) -> None:
    team.start(EDITOR, f"One, {mention(VIEWER)}")
    team.start(EDITOR, f"Two, {mention(VIEWER)}")

    assert team.tick() == 2


def test_replies_batch_into_a_count(team: Team) -> None:
    team.settings(EDITOR, mention=True, reply=True)
    thread = team.start(EDITOR)
    team.reply(APPROVER, thread)
    team.reply(VIEWER, thread)

    team.tick()

    (message,) = team.mail.sent
    assert message.to == EDITOR.email
    assert "2 new replies" in message.subject


def test_what_was_read_before_the_email_is_not_sent(team: Team) -> None:
    team.start(EDITOR, f"Over to {mention(VIEWER)}")
    team.as_(VIEWER).post("/api/v1/me/notifications/read-all")

    assert team.tick() == 0


def test_an_email_names_who_where_and_a_link_and_never_the_comment(team: Team) -> None:
    thread = team.start(EDITOR, f"{PRIVATE_WORDS}, {mention(VIEWER)}")

    team.tick()

    (message,) = team.mail.sent
    comment = thread["comments"][0]["id"]
    link = f"{BASE_URL}/projects/{DEMO_PROJECT_ID}/discussion?thread={thread['id']}"
    assert f"{link}&comment={comment}" in message.text
    for part in (message.subject, message.text, message.html):
        assert PRIVATE_WORDS not in part


def test_an_unreachable_email_service_is_retried_once_then_given_up(team: Team) -> None:
    team.start(EDITOR, f"Over to {mention(VIEWER)}")
    team.mail.fail = True
    attempts: list[object] = []
    send = team.mail.send
    team.mail.send = lambda message: (attempts.append(message), send(message))[1]  # type: ignore[method-assign]

    assert team.tick() == 0

    assert len(attempts) == 2
    assert team.inbox(VIEWER), "the notification itself stands"
    team.mail.fail = False
    assert team.tick(16) == 0


def test_a_failed_email_logs_no_address(team: Team, caplog: pytest.LogCaptureFixture) -> None:
    team.start(EDITOR, f"Over to {mention(VIEWER)}")
    team.mail.fail = True

    team.tick()

    assert caplog.records
    assert all(VIEWER.email not in str(vars(record)) for record in caplog.records)


def test_clean_up_deletes_only_notifications_past_ninety_days(team: Team) -> None:
    team.start(EDITOR, f"First, {mention(VIEWER)}")
    team.start(EDITOR, f"Second, {mention(VIEWER)}")
    kept, old = team.inbox(VIEWER)
    engine = create_database_engine(team.database_url)
    with create_session_factory(engine)() as session:
        session.query(NotificationRecord).filter_by(id=UUID(old["id"])).update(
            {"created_at": utc_now() - timedelta(days=91)}
        )
        session.commit()
    engine.dispose()

    team.tick()

    assert [n["id"] for n in team.inbox(VIEWER)] == [kept["id"]]


def test_the_activity_log_never_shows_mentions_or_comment_text(team: Team) -> None:
    team.start(EDITOR, f"{PRIVATE_WORDS}, {mention(VIEWER)}")

    events = team.as_(APPROVER).get(f"{PROJECT}/activity").json()["events"]

    assert all(PRIVATE_WORDS not in event["summary"] for event in events)
    assert not {"mentioned", "replied"} & {event["type"] for event in events}
