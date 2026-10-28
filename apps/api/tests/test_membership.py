"""Sign-up, invitations by link or email, member roles, removal and leaving, through the API with
session sign-in. Emails go to an in-memory sender; every account and project is synthetic."""

import logging
import re
import secrets
from collections.abc import Callable
from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import select, update

from scopesteps.api.seed import DEMO_PROJECT_ID, LOCAL_REVIEWER, SEED_ACCOUNTS, seed
from scopesteps.identity.http import router as identity_router
from scopesteps.identity.infrastructure.email import RecordingEmailSender
from scopesteps.identity.infrastructure.orm import (
    EmailTokenRecord,
    InvitationRecord,
    UserRecord,
)
from scopesteps.identity.infrastructure.passwords import Argon2PasswordHasher
from scopesteps.identity.infrastructure.repository import SqlMemberStore
from scopesteps.infrastructure.database import (
    create_database_engine,
    create_session_factory,
    utc_now,
)

ClientFactory = Callable[..., TestClient]
Json = dict[str, Any]

BASE_URL = "https://app.scopesteps.test"
PROJECT = f"/api/v1/projects/{DEMO_PROJECT_ID}"
MEMBERS = f"{PROJECT}/members"
INVITATIONS = f"{PROJECT}/invitations"
VIEWER, EDITOR, APPROVER = SEED_ACCOUNTS
NEWCOMER = "new.person@example.test"
STRONG = "a-long-enough-passphrase"
LINK = re.compile(rf"{re.escape(BASE_URL)}/(?:invite|verify-email)/([A-Za-z0-9_-]+)")
WEAK_HASHER = Argon2PasswordHasher(PasswordHasher(time_cost=1, memory_cost=8, parallelism=1))


class World:
    """The demo project with its seeded approver, editor and viewer, each in their own browser."""

    def __init__(self, make_client: ClientFactory, database_url: str, password: str) -> None:
        self.make_client = make_client
        self.database_url = database_url
        self.password = password
        self.mail = RecordingEmailSender()
        self.browsers: dict[str, TestClient] = {}

    def browser(self, name: str = "anonymous", **client: Any) -> TestClient:
        if name not in self.browsers:
            app_client = self.make_client(
                self.database_url, auth_mode="session", app_base_url=BASE_URL, **client
            )
            app_client.app.state.email_sender = self.mail  # type: ignore[attr-defined]
            self.browsers[name] = app_client
        return self.browsers[name]

    def signed_in(self, email: str, password: str | None = None) -> TestClient:
        client = self.browser(email)
        if client.get("/api/v1/me").status_code != 200:
            response = client.post(
                "/api/v1/auth/sign-in", json={"email": email, "password": password or self.password}
            )
            assert response.status_code == 200, response.text
        return client

    @property
    def approver(self) -> TestClient:
        return self.signed_in(APPROVER.email)

    def invite(
        self, email: str = NEWCOMER, roles: list[str] | None = None, **body: Any
    ) -> Response:
        return self.approver.post(
            MEMBERS,
            json={"email": email, "roles": roles or ["viewer"], "send_email": False} | body,
        )

    def invitation_link(self, email: str = NEWCOMER, roles: list[str] | None = None) -> str:
        response = self.invite(email, roles)
        assert response.status_code == 201, response.text
        return response.json()["link"]

    def last_link(self, to: str) -> str:
        message = next(m for m in reversed(self.mail.sent) if m.to == to)
        found = LINK.search(message.text)
        assert found is not None, message.text
        return found.group(0)

    def members(self, client: TestClient | None = None) -> list[Json]:
        response = (client or self.approver).get(MEMBERS)
        assert response.status_code == 200, response.text
        return response.json()["members"]

    def member(self, user_id: UUID) -> Json:
        return next(m for m in self.members() if m["user_id"] == str(user_id))

    def events(self, *types: str) -> list[Json]:
        feed = self.approver.get(f"{PROJECT}/activity").json()["events"]
        return [e for e in feed if not types or e["type"] in types]

    def rows(self, statement: Any) -> list[tuple[Any, ...]]:
        engine = create_database_engine(self.database_url)
        with create_session_factory(engine)() as session:
            rows: list[tuple[Any, ...]] = [tuple(row) for row in session.execute(statement)]
        engine.dispose()
        return rows

    def execute(self, statement: Any) -> None:
        engine = create_database_engine(self.database_url)
        with create_session_factory(engine)() as session:
            session.execute(statement)
            session.commit()
        engine.dispose()


@pytest.fixture
def world(migrated_database_url: str, make_client: ClientFactory) -> World:
    password = secrets.token_urlsafe(16)
    engine = create_database_engine(migrated_database_url)
    with create_session_factory(engine)() as session:
        seed(session, account_password=password, hasher=WEAK_HASHER)
    engine.dispose()
    return World(make_client, migrated_database_url, password)


def _error(response: Response, status: int, code: str) -> Json:
    assert response.status_code == status, response.text
    body: Json = response.json()
    assert body["code"] == code, body
    return body


def _token(link: str) -> str:
    return link.rsplit("/", 1)[1]


OUTSIDER = "outsider@example.test"


def _outsider(world: World) -> TestClient:
    """A confirmed account that is not in the project, signed in in its own browser."""
    browser = world.browser(OUTSIDER)
    _sign_up(browser, email=OUTSIDER, display_name="Out Sider")
    confirmed = browser.post(
        "/api/v1/auth/verify-email", json={"token": _token(world.last_link(OUTSIDER))}
    )
    assert confirmed.status_code == 200, confirmed.text
    world.mail.sent.clear()
    return browser


def _sign_up(client: TestClient, email: str = NEWCOMER, **body: Any) -> Response:
    return client.post(
        "/api/v1/auth/sign-up",
        json={"display_name": "New Person", "email": email, "password": STRONG} | body,
    )


# Accounts and sign-up


def test_sign_up_answers_the_same_and_emails_a_new_or_existing_owner(world: World) -> None:
    browser = world.browser()

    new = _sign_up(browser)
    existing = _sign_up(browser, email=EDITOR.email.upper())

    assert (new.status_code, existing.status_code) == (202, 202)
    assert new.json() == existing.json()
    to_new, to_existing = world.mail.sent
    assert (to_new.to, to_new.subject) == (NEWCOMER, "Confirm your email address for ScopeSteps")
    assert f"{BASE_URL}/verify-email/" in to_new.text
    assert (to_existing.to, to_existing.subject) == (
        EDITOR.email,
        "You already have a ScopeSteps account",
    )
    assert f"{BASE_URL}/sign-in" in to_existing.text
    users = world.rows(select(UserRecord.email, UserRecord.email_verified_at))
    assert (NEWCOMER, None) in [tuple(u) for u in users]
    assert sum(1 for (email, _) in users if email == EDITOR.email) == 1


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ({"password": "too-short"}, "INVALID_INPUT"),
        ({"email": "not-an-email"}, "EMAIL_INVALID"),
        ({"display_name": "   "}, "PROFILE_INVALID"),
    ],
)
def test_sign_up_refuses_a_weak_password_or_a_malformed_field(
    world: World, body: Json, code: str
) -> None:
    response = _sign_up(world.browser(), **body)

    _error(response, 422, code)
    assert world.mail.sent == []


def test_the_confirmation_link_works_once_and_signs_in(world: World) -> None:
    browser = world.browser()
    _sign_up(browser)
    token = _token(world.last_link(NEWCOMER))

    refused = browser.post("/api/v1/auth/sign-in", json={"email": NEWCOMER, "password": STRONG})
    confirmed = browser.post("/api/v1/auth/verify-email", json={"token": token})
    again = world.browser("other").post("/api/v1/auth/verify-email", json={"token": token})

    _error(refused, 403, "EMAIL_NOT_VERIFIED")
    assert confirmed.status_code == 200, confirmed.text
    assert (confirmed.json()["email"], confirmed.json()["memberships"]) == (NEWCOMER, [])
    assert browser.get("/api/v1/me").json()["email"] == NEWCOMER
    assert browser.get("/api/v1/projects").json()["projects"] == [], "no projects until invited"
    _error(again, 404, "TOKEN_INVALID")


def test_an_expired_confirmation_link_is_refused_and_a_new_one_can_be_sent(world: World) -> None:
    browser = world.browser()
    _sign_up(browser)
    expired = _token(world.last_link(NEWCOMER))
    world.execute(update(EmailTokenRecord).values(expires_at=utc_now() - timedelta(seconds=1)))

    refused = browser.post("/api/v1/auth/verify-email", json={"token": expired})
    resent = browser.post("/api/v1/auth/resend-verification", json={"email": NEWCOMER})
    unknown = browser.post("/api/v1/auth/resend-verification", json={"email": "who@example.test"})

    _error(refused, 404, "TOKEN_INVALID")
    assert (resent.status_code, resent.json()) == (202, unknown.json())
    fresh = _token(world.last_link(NEWCOMER))
    assert fresh != expired
    assert browser.post("/api/v1/auth/verify-email", json={"token": fresh}).status_code == 200
    assert [m.to for m in world.mail.sent] == [NEWCOMER, NEWCOMER], "nothing for an unknown one"


def test_an_unconfirmed_sign_in_is_told_only_with_the_right_password(world: World) -> None:
    browser = world.browser()
    _sign_up(browser)

    wrong = browser.post(
        "/api/v1/auth/sign-in", json={"email": NEWCOMER, "password": "wrong!x" * 3}
    )
    right = browser.post("/api/v1/auth/sign-in", json={"email": NEWCOMER, "password": STRONG})

    _error(wrong, 401, "INVALID_CREDENTIALS")
    _error(right, 403, "EMAIL_NOT_VERIFIED")


def test_the_sixth_sign_up_from_one_address_in_an_hour_is_refused(world: World) -> None:
    browser = world.browser()

    answers = [_sign_up(browser, email=f"person{n}@example.test") for n in range(6)]

    assert [a.status_code for a in answers[:5]] == [202] * 5
    body = _error(answers[5], 429, "RATE_LIMITED")
    assert body["retryable"] is True
    assert len(world.mail.sent) == 5


def test_the_fourth_sign_up_for_one_email_in_an_hour_is_refused(world: World) -> None:
    browsers = [world.browser(f"b{n}", client=("127.0.0.1", 50000 + n)) for n in range(4)]

    answers = [_sign_up(browser) for browser in browsers]

    assert [a.status_code for a in answers[:3]] == [202] * 3
    _error(answers[3], 429, "RATE_LIMITED")


def test_signing_up_again_takes_over_an_address_nobody_confirmed(world: World) -> None:
    squatters = secrets.token_urlsafe(16)
    _sign_up(world.browser("squatter"), display_name="Squatter", password=squatters)
    browser = world.browser("owner")

    _sign_up(browser, display_name="Real Owner")
    confirmed = browser.post(
        "/api/v1/auth/verify-email", json={"token": _token(world.last_link(NEWCOMER))}
    )

    assert confirmed.json()["display_name"] == "Real Owner"
    squatter = world.browser("squatter").post(
        "/api/v1/auth/sign-in", json={"email": NEWCOMER, "password": squatters}
    )
    _error(squatter, 401, "INVALID_CREDENTIALS")


# Inviting


def test_an_approver_invites_an_email_with_and_without_an_account(world: World) -> None:
    _outsider(world)

    with_account = world.invite(OUTSIDER.upper(), ["editor"])
    without = world.invite(NEWCOMER, ["viewer", "editor"])

    assert (with_account.status_code, without.status_code) == (201, 201)
    for response, email in ((with_account, OUTSIDER), (without, NEWCOMER)):
        body = response.json()
        assert body["email_sent"] is False
        assert body["link"].startswith(f"{BASE_URL}/invite/")
        assert body["invitation"]["email"] == email
        assert body["invitation"]["expired"] is False
        created, expires = body["invitation"]["created_at"], body["invitation"]["expires_at"]
        assert expires > created
    listed = world.approver.get(INVITATIONS).json()["invitations"]
    assert {i["email"] for i in listed} == {OUTSIDER, NEWCOMER}
    assert world.mail.sent == []


def test_an_invitation_email_names_inviter_project_roles_link_and_expiry_only(
    world: World,
) -> None:
    world.approver.post(
        f"{PROJECT}/sources",
        files={"brief": ("brief.md", b"# Secret plan\n\nA confidential paragraph.")},
        headers={"Idempotency-Key": "upload-key-0001"},
    )

    response = world.invite(NEWCOMER, ["viewer", "approver"], send_email=True)

    body = response.json()
    assert (body["email_sent"], body["link"]) == (True, None)
    (message,) = world.mail.sent
    assert message.to == NEWCOMER
    assert message.subject == "You're invited to Campus Room Booking on ScopeSteps"
    for part in (message.text, message.html):
        assert APPROVER.display_name in part
        assert "Campus Room Booking" in part
        assert "Viewer and Approver" in part
        assert f"{BASE_URL}/invite/" in part
        assert "expires on" in part
        assert "confidential" not in part.lower()
    assert world.events("invitation.emailed")


def test_names_in_an_invitation_email_are_escaped_in_html(world: World) -> None:
    world.approver.patch(
        "/api/v1/me",
        json={"display_name": "<b>Ann</b>", "expected_revision": 1},
    )

    world.invite(NEWCOMER, send_email=True)

    (message,) = world.mail.sent
    assert "&lt;b&gt;Ann&lt;/b&gt;" in message.html
    assert "<b>Ann</b>" not in message.html


@pytest.mark.parametrize(
    ("roles", "status"), [([], 422), (["workspace_admin"], 422), (["integration_admin"], 422)]
)
def test_an_invitation_needs_grantable_roles(world: World, roles: list[str], status: int) -> None:
    response = world.approver.post(MEMBERS, json={"email": NEWCOMER, "roles": roles})

    assert response.status_code == status
    assert world.approver.get(INVITATIONS).json()["invitations"] == []


def test_a_member_or_an_open_invitation_cannot_be_invited_again(world: World) -> None:
    world.invite(NEWCOMER)

    member = world.invite(EDITOR.email)
    duplicate = world.invite(NEWCOMER.upper())

    _error(member, 409, "ALREADY_MEMBER")
    _error(duplicate, 409, "ALREADY_INVITED")


def test_the_twenty_first_invitation_email_in_an_hour_is_refused(world: World) -> None:
    emails = [world.invite(f"p{n}@example.test", send_email=True) for n in range(21)]

    assert [e.status_code for e in emails[:20]] == [201] * 20
    _error(emails[20], 429, "RATE_LIMITED")
    assert len(world.mail.sent) == 20
    assert len(world.approver.get(INVITATIONS).json()["invitations"]) == 20, "refused stores none"


def test_a_failed_invitation_email_keeps_the_invitation_and_returns_its_link(
    world: World,
) -> None:
    world.mail.fail = True

    response = world.invite(NEWCOMER, send_email=True)
    invitation_id = response.json()["invitation"]["id"]
    resend = world.approver.post(f"{INVITATIONS}/{invitation_id}/email")

    body = response.json()
    assert (response.status_code, body["email_sent"]) == (201, False)
    assert body["link"].startswith(f"{BASE_URL}/invite/")
    _error(resend, 502, "EMAIL_FAILED")
    assert world.events("invitation.emailed") == []


# Joining


def test_the_invited_account_joins_with_its_roles(world: World) -> None:
    outsider = _outsider(world)
    (user_id,) = (UUID(outsider.get("/api/v1/me").json()["id"]),)
    link = world.invitation_link(OUTSIDER, ["editor", "viewer"])

    preview = world.browser().get(f"/api/v1/invitations/{_token(link)}")
    joined = outsider.post(f"/api/v1/invitations/{_token(link)}/accept")

    assert preview.status_code == 200, preview.text
    assert preview.json() | {"expires_at": None} == {
        "project_id": str(DEMO_PROJECT_ID),
        "project_name": "Campus Room Booking",
        "invited_by_name": APPROVER.display_name,
        "email": OUTSIDER,
        "roles": ["viewer", "editor"],
        "expires_at": None,
        "has_account": True,
    }
    assert joined.status_code == 200, joined.text
    assert joined.json()["project_id"] == str(DEMO_PROJECT_ID)
    assert set(world.member(user_id)["roles"]) == {"viewer", "editor"}
    assert [p["id"] for p in outsider.get("/api/v1/projects").json()["projects"]] == [
        str(DEMO_PROJECT_ID)
    ]


def test_another_account_cannot_use_an_invitation(world: World) -> None:
    link = world.invitation_link(NEWCOMER)

    response = world.signed_in(EDITOR.email).post(f"/api/v1/invitations/{_token(link)}/accept")

    _error(response, 403, "INVITATION_EMAIL_MISMATCH")
    assert world.approver.get(INVITATIONS).json()["invitations"][0]["email"] == NEWCOMER


def test_someone_without_an_account_creates_it_from_the_link_and_lands_in_the_project(
    world: World,
) -> None:
    token = _token(world.invitation_link(NEWCOMER, ["editor"]))
    browser = world.browser()

    preview = browser.get(f"/api/v1/invitations/{token}").json()
    joined = browser.post(
        f"/api/v1/invitations/{token}/sign-up",
        json={"display_name": "New Person", "password": STRONG},
    )

    assert preview["has_account"] is False
    assert joined.status_code == 200, joined.text
    assert joined.json()["user"]["email"] == NEWCOMER
    assert browser.get("/api/v1/me").json()["display_name"] == "New Person", "signed in"
    assert [p["id"] for p in browser.get("/api/v1/projects").json()["projects"]] == [
        str(DEMO_PROJECT_ID)
    ]
    ((verified,),) = world.rows(
        select(UserRecord.email_verified_at).where(UserRecord.email == NEWCOMER)
    )
    assert verified is not None, "the link proved the address"
    assert world.mail.sent == []


def test_link_sign_up_is_refused_when_the_email_has_an_account(world: World) -> None:
    _outsider(world)
    token = _token(world.invitation_link(OUTSIDER))

    response = world.browser().post(
        f"/api/v1/invitations/{token}/sign-up",
        json={"display_name": "Impostor", "password": STRONG},
    )

    _error(response, 409, "ACCOUNT_EXISTS")


def test_a_link_works_once_and_not_once_replaced_cancelled_or_expired(world: World) -> None:
    used = _token(world.invitation_link(NEWCOMER))
    world.browser().post(
        f"/api/v1/invitations/{used}/sign-up", json={"display_name": "A", "password": STRONG}
    )
    replaced = world.invite("replaced@example.test").json()
    renewed = world.approver.post(f"{INVITATIONS}/{replaced['invitation']['id']}/link").json()
    cancelled = world.invite("cancelled@example.test").json()
    world.approver.delete(f"{INVITATIONS}/{cancelled['invitation']['id']}")
    expired = world.invitation_link("expired@example.test")
    world.execute(
        update(InvitationRecord)
        .where(InvitationRecord.email == "expired@example.test")
        .values(expires_at=utc_now() - timedelta(seconds=1))
    )

    for token in (
        used,
        _token(replaced["link"]),
        _token(cancelled["link"]),
        _token(expired),
        "not-a-real-token-at-all",
    ):
        _error(world.browser().get(f"/api/v1/invitations/{token}"), 404, "INVITATION_INVALID")
    assert world.browser().get(f"/api/v1/invitations/{_token(renewed['link'])}").status_code == 200
    listed = {i["email"]: i for i in world.approver.get(INVITATIONS).json()["invitations"]}
    assert listed["expired@example.test"]["expired"] is True
    assert "cancelled@example.test" not in listed


# Roles, removal and leaving


@pytest.mark.parametrize("who", [EDITOR, VIEWER])
def test_editors_and_viewers_manage_no_members(world: World, who: Any) -> None:
    invitation = world.invite("someone@example.test").json()["invitation"]
    client = world.signed_in(who.email)
    member = world.member(VIEWER.id)

    attempts = [
        client.post(MEMBERS, json={"email": "x@example.test", "roles": ["viewer"]}),
        client.get(INVITATIONS),
        client.post(f"{INVITATIONS}/{invitation['id']}/link"),
        client.post(f"{INVITATIONS}/{invitation['id']}/email"),
        client.delete(f"{INVITATIONS}/{invitation['id']}"),
        client.put(
            f"{MEMBERS}/{APPROVER.id}/roles",
            json={"roles": ["viewer"], "expected_revision": member["revision"]},
        ),
        client.delete(f"{MEMBERS}/{APPROVER.id}"),
    ]

    for response in attempts:
        _error(response, 403, "PERMISSION_DENIED")
    assert world.members(client), "they still read the members"


def test_a_non_member_sees_no_members_or_invitations(world: World) -> None:
    browser = world.browser()
    _sign_up(browser, email="outsider@example.test")
    browser.post(
        "/api/v1/auth/verify-email",
        json={"token": _token(world.last_link("outsider@example.test"))},
    )

    for response in (
        browser.get(MEMBERS),
        browser.get(INVITATIONS),
        browser.post(MEMBERS, json={"email": "a@b.test", "roles": ["viewer"]}),
    ):
        _error(response, 404, "NOT_FOUND")


def test_an_approver_changes_roles_at_the_revision_they_read(world: World) -> None:
    before = world.member(EDITOR.id)

    changed = world.approver.put(
        f"{MEMBERS}/{EDITOR.id}/roles",
        json={"roles": ["editor", "approver"], "expected_revision": before["revision"]},
    )
    stale = world.approver.put(
        f"{MEMBERS}/{EDITOR.id}/roles",
        json={"roles": ["viewer"], "expected_revision": before["revision"]},
    )

    assert changed.status_code == 200, changed.text
    assert changed.json()["roles"] == ["editor", "approver"]
    assert changed.json()["revision"] == before["revision"] + 1
    _error(stale, 409, "MEMBER_CHANGED")
    assert set(world.member(EDITOR.id)["roles"]) == {"editor", "approver"}
    assert set(world.signed_in(EDITOR.email).get(PROJECT).json()["roles"]) >= {"approver"}


def test_a_removed_member_loses_access_at_once_and_keeps_their_name_on_past_work(
    world: World,
) -> None:
    editor = world.signed_in(EDITOR.email)
    uploaded = editor.post(
        f"{PROJECT}/sources",
        files={"brief": ("brief.md", b"# Notes\n\nStudents book rooms.")},
        headers={"Idempotency-Key": "upload-key-0002"},
    )
    assert uploaded.status_code == 201, uploaded.text

    removed = world.approver.delete(f"{MEMBERS}/{EDITOR.id}")

    assert removed.status_code == 204
    _error(editor.get(PROJECT), 404, "NOT_FOUND")
    assert str(DEMO_PROJECT_ID) not in {
        p["id"] for p in editor.get("/api/v1/projects").json()["projects"]
    }
    (added,) = world.events("source.added")
    assert added["actor"]["display_name"] == EDITOR.display_name
    assert all(m["user_id"] != str(EDITOR.id) for m in world.members())


def test_any_member_may_leave(world: World) -> None:
    viewer = world.signed_in(VIEWER.email)

    left = viewer.delete(f"{MEMBERS}/{VIEWER.id}")

    assert left.status_code == 204
    _error(viewer.get(PROJECT), 404, "NOT_FOUND")
    (event,) = world.events("member.left")
    assert event["summary"] == f"{VIEWER.display_name} left the project"


def _sole_approver(world: World) -> None:
    """Leave the seeded approver as the project's only approver."""
    reviewer = world.member(LOCAL_REVIEWER.id)
    response = world.approver.put(
        f"{MEMBERS}/{LOCAL_REVIEWER.id}/roles",
        json={"roles": ["editor"], "expected_revision": reviewer["revision"]},
    )
    assert response.status_code == 200, response.text


def test_the_last_approver_cannot_leave_be_removed_or_drop_the_role(world: World) -> None:
    _sole_approver(world)
    me = world.member(APPROVER.id)

    attempts = [
        world.approver.delete(f"{MEMBERS}/{APPROVER.id}"),
        world.approver.put(
            f"{MEMBERS}/{APPROVER.id}/roles",
            json={"roles": ["editor"], "expected_revision": me["revision"]},
        ),
    ]

    for response in attempts:
        body = _error(response, 409, "LAST_APPROVER")
        assert "Make someone else approver first" in body["message"]
    assert "approver" in world.member(APPROVER.id)["roles"]


def test_two_approvers_leaving_at_once_leave_one(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sole_approver(world)
    editor = world.member(EDITOR.id)
    promoted = world.approver.put(
        f"{MEMBERS}/{EDITOR.id}/roles",
        json={"roles": ["editor", "approver"], "expected_revision": editor["revision"]},
    )
    assert promoted.status_code == 200, promoted.text
    second_approver = world.signed_in(EDITOR.email)

    first = world.approver.delete(f"{MEMBERS}/{APPROVER.id}")

    class ReadBeforeTheOtherCommitted(SqlMemberStore):
        """The second approver's request read the members before the first one left."""

        def roles_by_member(self, project_id: Any) -> Any:
            return super().roles_by_member(project_id) | {APPROVER.id: frozenset({"approver"})}

    monkeypatch.setattr(identity_router, "SqlMemberStore", ReadBeforeTheOtherCommitted)
    second = second_approver.delete(f"{MEMBERS}/{EDITOR.id}")
    monkeypatch.undo()

    assert first.status_code == 204
    _error(second, 409, "LAST_APPROVER")
    approvers = [m["user_id"] for m in world.members(second_approver) if "approver" in m["roles"]]
    assert approvers == [str(EDITOR.id)]


def test_a_removal_that_would_leave_no_approver_after_a_stale_read_is_rolled_back(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sole_approver(world)

    class SawAnotherApprover(SqlMemberStore):
        def roles_by_member(self, project_id: Any) -> Any:
            roles = super().roles_by_member(project_id)
            return roles | {LOCAL_REVIEWER.id: frozenset({"approver"})}

    monkeypatch.setattr(identity_router, "SqlMemberStore", SawAnotherApprover)
    response = world.approver.delete(f"{MEMBERS}/{APPROVER.id}")

    _error(response, 409, "LAST_APPROVER")
    monkeypatch.undo()
    assert "approver" in world.member(APPROVER.id)["roles"]
    assert world.events("member.left") == []


# Activity log, tokens and email addresses


def test_each_membership_action_records_one_event_without_email_addresses(world: World) -> None:
    invited = world.invite(NEWCOMER, ["viewer"]).json()
    link = world.approver.post(f"{INVITATIONS}/{invited['invitation']['id']}/link").json()["link"]
    world.approver.post(f"{INVITATIONS}/{invited['invitation']['id']}/email")
    cancelled = world.invite("gone@example.test").json()
    world.approver.delete(f"{INVITATIONS}/{cancelled['invitation']['id']}")
    world.browser().post(
        f"/api/v1/invitations/{_token(world.last_link(NEWCOMER))}/sign-up",
        json={"display_name": "New Person", "password": STRONG},
    )
    world.approver.put(
        f"{MEMBERS}/{VIEWER.id}/roles",
        json={"roles": ["editor"], "expected_revision": world.member(VIEWER.id)["revision"]},
    )
    world.approver.delete(f"{MEMBERS}/{VIEWER.id}")
    world.signed_in(EDITOR.email).delete(f"{MEMBERS}/{EDITOR.id}")
    assert link

    events = list(reversed(world.events()))

    assert [(e["type"], e["summary"]) for e in events] == [
        ("member.invited", "Invited someone as Viewer"),
        ("invitation.link_created", "Made a new invitation link"),
        ("invitation.emailed", "Emailed an invitation"),
        ("member.invited", "Invited someone as Viewer"),
        ("invitation.cancelled", "Cancelled an invitation as Viewer"),
        ("invitation.accepted", "Joined the project as Viewer"),
        ("member.roles_changed", f"Changed {VIEWER.display_name}'s roles to Editor"),
        ("member.removed", f"Removed {VIEWER.display_name} from the project"),
        ("member.left", f"{EDITOR.display_name} left the project"),
    ]
    assert events[5]["actor"]["display_name"] == "New Person"
    text = str(events)
    assert "@" not in text, "no email address in the log"


def test_refused_membership_actions_record_nothing(world: World) -> None:
    _sole_approver(world)
    before = len(world.events())

    world.invite(EDITOR.email)
    world.approver.delete(f"{MEMBERS}/{APPROVER.id}")
    world.signed_in(VIEWER.email).post(MEMBERS, json={"email": "a@b.test", "roles": ["viewer"]})

    assert len(world.events()) == before


def test_raw_tokens_are_never_stored_or_logged(
    world: World, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    _sign_up(world.browser())
    confirm = _token(world.last_link(NEWCOMER))
    invite = _token(world.invitation_link("invited@example.test"))
    world.browser().get(f"/api/v1/invitations/{invite}")

    stored = str(world.rows(select(InvitationRecord.token_hash, EmailTokenRecord.token_hash)))
    # The test client logs the URLs it requests; the server is what must not.
    logged = "\n".join(
        r.getMessage() for r in caplog.records if not r.name.startswith(("httpx", "httpcore"))
    )
    for token in (confirm, invite):
        assert token not in stored
        assert token not in logged
    assert NEWCOMER not in logged, "nor an email address"


def test_access_log_lines_hide_an_invitation_token() -> None:
    from scopesteps.api.redaction import LinkTokenFilter

    token = secrets.token_urlsafe(32)
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:1", "GET", f"/api/v1/invitations/{token}", "1.1", 200),
        None,
    )

    LinkTokenFilter().filter(record)

    assert token not in record.getMessage()
    assert "/api/v1/invitations/[redacted]" in record.getMessage()
