import secrets
from collections.abc import Callable
from typing import Any
from uuid import UUID

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from httpx2 import Response

from scopesteps.api.seed import DEMO_PROJECT_ID, LOCAL_REVIEWER_ID, SEED_ACCOUNTS, seed
from scopesteps.identity.infrastructure.passwords import Argon2PasswordHasher
from scopesteps.infrastructure.database import create_database_engine, create_session_factory

ClientFactory = Callable[..., TestClient]
Json = dict[str, Any]

ME = "/api/v1/me"
MEMBERS = f"/api/v1/projects/{DEMO_PROJECT_ID}/members"
VIEWER, EDITOR, _APPROVER = (account.email for account in SEED_ACCOUNTS)
WEAK_HASHER = Argon2PasswordHasher(PasswordHasher(time_cost=1, memory_cost=8, parallelism=1))


def _update(
    client: TestClient,
    display_name: str = "Dana Reviewer",
    job_title: str = "Product owner",
    about: str = "",
    expected_revision: int = 1,
) -> Response:
    return client.patch(
        ME,
        json={
            "display_name": display_name,
            "job_title": job_title,
            "about": about,
            "expected_revision": expected_revision,
        },
    )


def _members(client: TestClient) -> list[Json]:
    response = client.get(MEMBERS)
    assert response.status_code == 200
    return response.json()["members"]


def test_a_new_profile_starts_with_the_seeded_name_and_no_title(client: TestClient) -> None:
    body = client.get(ME).json()

    assert (body["display_name"], body["job_title"], body["about"]) == ("Local Reviewer", "", "")
    assert body["revision"] == 1


def test_updating_the_profile_stores_it_trimmed_and_moves_the_revision(
    client: TestClient,
) -> None:
    response = _update(
        client,
        display_name="  Dana   Reviewer ",
        job_title=" Product\towner ",
        about="  Runs the booking pilot.\r\nAsk me about rooms.  ",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["display_name"] == "Dana Reviewer"
    assert body["job_title"] == "Product owner"
    assert body["about"] == "Runs the booking pilot.\nAsk me about rooms."
    assert body["revision"] == 2
    assert client.get(ME).json() == body


@pytest.mark.parametrize(
    ("change", "field", "max_chars"),
    [
        ({"display_name": ""}, "display_name", 60),
        ({"display_name": " \t "}, "display_name", 60),
        ({"display_name": "n" * 61}, "display_name", 60),
        ({"display_name": "Dana​Reviewer"}, "display_name", 60),
        ({"job_title": "t" * 81}, "job_title", 80),
        ({"about": "a" * 281}, "about", 280),
        ({"about": "Bell\x07"}, "about", 280),
    ],
    ids=["blank", "spaces", "name-61", "zero-width", "title-81", "about-281", "control"],
)
def test_invalid_profiles_are_rejected_and_nothing_is_stored(
    client: TestClient, change: Json, field: str, max_chars: int
) -> None:
    response = _update(client, **change)

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "PROFILE_INVALID"
    assert body["details"] == {"field": field, "max_chars": max_chars}
    assert client.get(ME).json()["revision"] == 1


def test_the_longest_allowed_values_are_accepted(client: TestClient) -> None:
    response = _update(client, display_name="n" * 60, job_title="t" * 80, about="a" * 280)

    assert response.status_code == 200


def test_a_stale_revision_is_a_conflict_and_keeps_the_newer_profile(client: TestClient) -> None:
    _update(client, display_name="First Save")

    response = _update(client, display_name="Second Save", expected_revision=1)

    assert response.status_code == 409
    assert response.json()["code"] == "PROFILE_CHANGED"
    assert client.get(ME).json()["display_name"] == "First Save"


def test_repeating_a_save_succeeds_without_a_new_revision(client: TestClient) -> None:
    first = _update(client)

    retry = _update(client, expected_revision=1)

    assert retry.status_code == 200
    assert retry.json() == first.json()
    assert retry.json()["revision"] == 2


def test_email_and_roles_cannot_be_changed_through_the_profile(client: TestClient) -> None:
    before = client.get(ME).json()

    response = client.patch(
        ME,
        json={
            "display_name": "Dana Reviewer",
            "expected_revision": 1,
            "email": "someone-else@scopesteps.local",
            "memberships": [],
        },
    )

    assert response.status_code == 200
    after = response.json()
    assert after["email"] == before["email"]
    assert after["memberships"] == before["memberships"]


def test_members_are_listed_by_name_with_their_roles_and_no_email(client: TestClient) -> None:
    members = _members(client)

    assert [m["display_name"] for m in members] == [
        "Local Reviewer",
        "Sample Approver",
        "Sample Editor",
        "Sample Viewer",
    ]
    reviewer = members[0]
    assert reviewer == {
        "user_id": str(LOCAL_REVIEWER_ID),
        "display_name": "Local Reviewer",
        "job_title": "",
        "roles": ["editor", "approver"],
    }
    assert all("email" not in member for member in members)


def test_members_of_a_project_the_actor_is_not_in_are_not_found(client: TestClient) -> None:
    other = UUID("019a3a5e-0000-7000-8000-0000000000ff")

    response = client.get(f"/api/v1/projects/{other}/members")

    assert response.status_code == 404


@pytest.fixture
def password() -> str:
    return secrets.token_urlsafe(16)


@pytest.fixture
def accounts_database_url(migrated_database_url: str, password: str) -> str:
    engine = create_database_engine(migrated_database_url)
    with create_session_factory(engine)() as session:
        seed(session, account_password=password, hasher=WEAK_HASHER)
        session.commit()
    engine.dispose()
    return migrated_database_url


def _signed_in(
    make_client: ClientFactory, database_url: str, email: str, password: str
) -> TestClient:
    client = make_client(database_url, auth_mode="session")
    response = client.post("/api/v1/auth/sign-in", json={"email": email, "password": password})
    assert response.status_code == 200
    return client


def test_a_viewer_edits_their_own_profile_and_other_members_see_the_new_name(
    accounts_database_url: str, make_client: ClientFactory, password: str
) -> None:
    viewer = _signed_in(make_client, accounts_database_url, VIEWER, password)
    editor = _signed_in(make_client, accounts_database_url, EDITOR, password)

    response = _update(viewer, display_name="Riley Viewer", job_title="Student rep")

    assert response.status_code == 200
    listed = {m["user_id"]: m for m in _members(editor)}
    assert listed[response.json()["id"]]["display_name"] == "Riley Viewer"
    assert listed[response.json()["id"]]["job_title"] == "Student rep"
    assert editor.get(ME).json()["display_name"] == "Sample Editor"


def test_the_profile_requires_a_session(
    accounts_database_url: str, make_client: ClientFactory
) -> None:
    client = make_client(accounts_database_url, auth_mode="session")

    response = _update(client)

    assert response.status_code == 401
