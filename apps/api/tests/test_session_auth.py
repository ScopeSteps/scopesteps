import hashlib
import logging
import re
import secrets
from collections.abc import Callable, Iterator
from datetime import timedelta
from typing import Any

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import select, update

from scopesteps.api import seed as seed_command
from scopesteps.api.seed import DEMO_PROJECT_ID, LOCAL_REVIEWER, SEED_ACCOUNTS, seed
from scopesteps.api.settings import get_settings
from scopesteps.identity.infrastructure.orm import SessionRecord, UserRecord
from scopesteps.identity.infrastructure.passwords import Argon2PasswordHasher
from scopesteps.infrastructure.database import (
    create_database_engine,
    create_session_factory,
    utc_now,
)

ClientFactory = Callable[..., TestClient]

ME = "/api/v1/me"
SIGN_IN = "/api/v1/auth/sign-in"
SIGN_OUT = "/api/v1/auth/sign-out"
SOURCES = f"/api/v1/projects/{DEMO_PROJECT_ID}/sources"
PUBLIC_ROUTES = {("post", SIGN_IN), ("post", SIGN_OUT)}
COOKIE = "scopesteps_session"
WEB_ORIGIN = "http://localhost:5173"
OTHER_SITE = "https://other-site.example"
VIEWER, EDITOR, APPROVER = (account.email for account in SEED_ACCOUNTS)
FILES = {
    "brief": ("brief.md", b"# Room booking\n\nStudents book study rooms."),
    "transcript": ("transcript.txt", b"**Dana:** Keep it to single slots."),
}
# The smallest parameters Argon2 accepts, so seeding stays fast. The API hashes with the real
# defaults, which also makes every first sign-in exercise the rehash.
WEAK_HASHER = Argon2PasswordHasher(PasswordHasher(time_cost=1, memory_cost=8, parallelism=1))


@pytest.fixture
def password() -> str:
    return secrets.token_urlsafe(16)


@pytest.fixture
def accounts_database_url(migrated_database_url: str, password: str) -> str:
    _run(migrated_database_url, lambda s: seed(s, account_password=password, hasher=WEAK_HASHER))
    return migrated_database_url


@pytest.fixture
def api(accounts_database_url: str, make_client: ClientFactory) -> TestClient:
    return make_client(accounts_database_url, auth_mode="session")


def _run[T](database_url: str, work: Callable[[Any], T]) -> T:
    engine = create_database_engine(database_url)
    with create_session_factory(engine)() as session:
        result = work(session)
        session.commit()
    engine.dispose()
    return result


def _sign_in(client: TestClient, email: str, password: str) -> Response:
    return client.post(SIGN_IN, json={"email": email, "password": password})


def _me_presenting(client: TestClient, token: str) -> Response:
    """Asks who the client is with exactly this session cookie, whatever its jar held."""
    client.cookies.clear()
    client.cookies.set(COOKIE, token)
    return client.get(ME)


def _without_request_id(response: Response) -> tuple[int, dict[str, Any]]:
    body = response.json()
    body.pop("request_id")
    return response.status_code, body


def test_me_requires_a_session(api: TestClient) -> None:
    response = api.get(ME)

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"


def test_every_module_route_requires_a_session(api: TestClient) -> None:
    paths: dict[str, dict[str, object]] = api.get("/openapi.json").json()["paths"]
    protected = [
        (method, path)
        for path, operations in paths.items()
        if path.startswith("/api/v1")
        for method in operations
        if (method, path) not in PUBLIC_ROUTES
    ]

    assert len(protected) > len(PUBLIC_ROUTES)
    for method, path in protected:
        url = re.sub(r"\{[^}]+\}", str(DEMO_PROJECT_ID), path)
        assert api.request(method, url).status_code == 401, f"{method.upper()} {path}"


def test_sign_in_sets_an_http_only_cookie_and_makes_its_user_the_current_user(
    api: TestClient, password: str
) -> None:
    response = _sign_in(api, EDITOR, password)

    assert response.status_code == 200
    assert response.json()["email"] == EDITOR
    assert response.headers["cache-control"] == "no-store"
    token = response.cookies[COOKIE]
    attributes = {part.strip().lower() for part in response.headers["set-cookie"].split(";")[1:]}
    assert attributes == {"httponly", "samesite=lax", "path=/", "max-age=43200"}
    assert len(token) >= 43, "at least 256 bits, URL-safe base64"
    assert token not in response.text
    me = api.get(ME)
    assert me.status_code == 200
    assert me.json() == response.json()
    assert me.json()["memberships"] == [{"project_id": str(DEMO_PROJECT_ID), "role": "editor"}]


def test_the_cookie_is_secure_and_host_bound_outside_local_development(
    accounts_database_url: str, make_client: ClientFactory, password: str
) -> None:
    client = make_client(accounts_database_url, auth_mode="session", app_env="production")

    cookie = _sign_in(client, EDITOR, password).headers["set-cookie"]

    assert cookie.startswith("__Host-scopesteps_session=")
    attributes = {part.strip().lower() for part in cookie.split(";")[1:]}
    assert {"secure", "httponly", "samesite=lax", "path=/"} <= attributes
    assert not any(attribute.startswith("domain") for attribute in attributes)


def test_email_is_matched_case_insensitively(api: TestClient, password: str) -> None:
    response = _sign_in(api, f"  {EDITOR.upper()} ", password)

    assert response.status_code == 200
    assert response.json()["email"] == EDITOR


def test_unknown_email_and_wrong_password_get_the_same_response(
    api: TestClient, password: str
) -> None:
    wrong_password = _sign_in(api, EDITOR, password + "x")
    unknown_email = _sign_in(api, "nobody@scopesteps.local", password)
    no_password_set = _sign_in(api, LOCAL_REVIEWER.email, password)

    expected: tuple[int, dict[str, Any]] = (
        401,
        {
            "code": "INVALID_CREDENTIALS",
            "message": "Email or password is incorrect",
            "retryable": False,
            "details": {},
        },
    )
    for response in (wrong_password, unknown_email, no_password_set):
        assert _without_request_id(response) == expected
        assert "set-cookie" not in response.headers
    assert set(wrong_password.headers) == set(unknown_email.headers)
    assert api.get(ME).status_code == 401


def test_passwords_are_stored_only_as_argon2id_hashes(
    api: TestClient, accounts_database_url: str, password: str
) -> None:
    _sign_in(api, EDITOR, password)

    hashes = _run(
        accounts_database_url,
        lambda s: {user.email: user.password_hash for user in s.scalars(select(UserRecord))},
    )

    assert hashes[LOCAL_REVIEWER.email] is None
    for email in (VIEWER, EDITOR, APPROVER):
        stored = hashes[email]
        assert stored is not None
        assert stored.startswith("$argon2id$")
        assert password not in stored
    assert len({hashes[VIEWER], hashes[EDITOR], hashes[APPROVER]}) == 3, "salted per account"


def test_a_hash_with_old_parameters_is_upgraded_at_sign_in(
    api: TestClient, accounts_database_url: str, password: str
) -> None:
    def editor_hash() -> str | None:
        query = select(UserRecord.password_hash).where(UserRecord.email == EDITOR)
        return _run(accounts_database_url, lambda s: s.scalar(query))

    seeded = editor_hash()

    _sign_in(api, EDITOR, password)

    upgraded = editor_hash()
    assert seeded is not None
    assert upgraded is not None
    assert WEAK_HASHER.needs_rehash(upgraded) != WEAK_HASHER.needs_rehash(seeded)
    assert not Argon2PasswordHasher().needs_rehash(upgraded)
    assert _sign_in(api, EDITOR, password).status_code == 200


def test_only_a_hash_of_the_session_token_is_stored(
    api: TestClient, accounts_database_url: str, password: str
) -> None:
    token = _sign_in(api, EDITOR, password).cookies[COOKIE]

    stored = _run(accounts_database_url, lambda s: s.scalars(select(SessionRecord)).all())

    assert [record.token_hash for record in stored] == [hashlib.sha256(token.encode()).hexdigest()]


def test_the_password_never_reaches_a_response_or_the_logs(
    api: TestClient, password: str, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)

    succeeded = _sign_in(api, EDITOR, password)
    refused = _sign_in(api, EDITOR, password + "x")
    invalid = api.post(SIGN_IN, json={"password": password})
    too_long = api.post(SIGN_IN, json={"email": EDITOR, "password": password * 100})

    assert [r.status_code for r in (succeeded, refused, invalid, too_long)] == [200, 401, 422, 422]
    for response in (succeeded, refused, invalid, too_long):
        assert password not in response.text
        assert "$argon2" not in response.text
    assert password not in caplog.text
    assert succeeded.cookies[COOKIE] not in caplog.text
    assert "Signed in" in caplog.text
    assert "Sign-in refused" in caplog.text


def test_sign_out_ends_the_session_on_the_server(
    api: TestClient, accounts_database_url: str, password: str
) -> None:
    token = _sign_in(api, EDITOR, password).cookies[COOKIE]

    response = api.post(SIGN_OUT)

    assert response.status_code == 204
    assert 'scopesteps_session="";' in response.headers["set-cookie"]
    assert "max-age=0" in response.headers["set-cookie"].lower()
    assert api.get(ME).status_code == 401
    assert _me_presenting(api, token).status_code == 401, "the old cookie is worthless"
    assert _run(accounts_database_url, lambda s: s.scalars(select(SessionRecord)).all()) == []


def test_sign_out_without_a_session_succeeds(api: TestClient) -> None:
    assert api.post(SIGN_OUT).status_code == 204


def test_signing_out_ends_only_that_session(
    accounts_database_url: str, make_client: ClientFactory, password: str
) -> None:
    laptop = make_client(accounts_database_url, auth_mode="session")
    phone = make_client(accounts_database_url, auth_mode="session")
    _sign_in(laptop, EDITOR, password)
    _sign_in(phone, EDITOR, password)

    laptop.post(SIGN_OUT)

    assert laptop.get(ME).status_code == 401
    assert phone.get(ME).status_code == 200


@pytest.mark.parametrize(
    ("column", "age", "status"),
    [
        ("expires_at", timedelta(seconds=1), 401),
        ("last_seen_at", timedelta(minutes=121), 401),
        ("last_seen_at", timedelta(minutes=119), 200),
    ],
)
def test_a_session_expires_at_its_absolute_lifetime_and_when_idle(
    api: TestClient,
    accounts_database_url: str,
    password: str,
    column: str,
    age: timedelta,
    status: int,
) -> None:
    _sign_in(api, EDITOR, password)
    _run(
        accounts_database_url,
        lambda s: s.execute(update(SessionRecord).values({column: utc_now() - age})),
    )

    response = api.get(ME)

    assert response.status_code == status
    if status == 401:
        assert response.json()["message"] == "Sign in to continue"


def test_session_lifetimes_come_from_settings(
    accounts_database_url: str, make_client: ClientFactory, password: str
) -> None:
    client = make_client(
        accounts_database_url,
        auth_mode="session",
        session_absolute_lifetime_minutes=30,
        session_idle_timeout_minutes=10,
    )

    cookie = _sign_in(client, EDITOR, password).headers["set-cookie"]
    _run(
        accounts_database_url,
        lambda s: s.execute(
            update(SessionRecord).values(last_seen_at=utc_now() - timedelta(minutes=11))
        ),
    )

    assert "Max-Age=1800" in cookie
    assert client.get(ME).status_code == 401


def test_a_request_extends_an_idle_session(
    api: TestClient, accounts_database_url: str, password: str
) -> None:
    _sign_in(api, EDITOR, password)
    an_hour_ago = utc_now() - timedelta(hours=1)
    _run(
        accounts_database_url,
        lambda s: s.execute(update(SessionRecord).values(last_seen_at=an_hour_ago)),
    )

    api.get(ME)

    last_seen = _run(accounts_database_url, lambda s: s.scalar(select(SessionRecord.last_seen_at)))
    assert last_seen is not None
    assert last_seen > an_hour_ago + timedelta(minutes=59)


def test_signing_in_again_replaces_the_session(api: TestClient, password: str) -> None:
    first = _sign_in(api, EDITOR, password).cookies[COOKIE]

    second = _sign_in(api, APPROVER, password).cookies[COOKIE]

    assert second != first
    assert api.get(ME).json()["email"] == APPROVER
    assert _me_presenting(api, first).status_code == 401


def test_a_cookie_planted_before_sign_in_never_becomes_the_session(
    api: TestClient, password: str
) -> None:
    planted = "token-planted-before-sign-in"
    api.cookies.set(COOKIE, planted)

    issued = _sign_in(api, EDITOR, password).cookies[COOKIE]

    assert issued != planted
    assert _me_presenting(api, planted).status_code == 401
    assert _me_presenting(api, issued).status_code == 200


@pytest.mark.parametrize(
    ("email", "status", "code"),
    [(VIEWER, 403, "PERMISSION_DENIED"), (APPROVER, 403, "PERMISSION_DENIED"), (EDITOR, 201, None)],
)
def test_project_role_checks_use_the_session_user(
    api: TestClient, password: str, email: str, status: int, code: str | None
) -> None:
    _sign_in(api, email, password)

    upload = api.post(SOURCES, files=FILES, headers={"Idempotency-Key": "upload-key-0001"})
    listing = api.get(SOURCES)

    assert upload.status_code == status
    assert upload.json().get("code") == code
    assert listing.status_code == 200, "every member may read"


def test_a_form_encoded_cross_site_post_is_refused(
    api: TestClient, accounts_database_url: str, password: str
) -> None:
    _sign_in(api, EDITOR, password)

    response = api.post(
        SIGN_OUT,
        data={"anything": "a form can carry"},
        headers={"Origin": OTHER_SITE, "Sec-Fetch-Site": "cross-site"},
    )

    assert response.status_code == 415
    body = response.json()
    assert body["code"] == "UNSUPPORTED_MEDIA_TYPE"
    assert body["request_id"] == response.headers["X-Request-ID"]
    assert api.get(ME).status_code == 200, "the session it tried to end is still there"


@pytest.mark.parametrize(
    "content_type",
    ["application/x-www-form-urlencoded", "text/plain", "text/plain; charset=utf-8", "text/json"],
)
def test_sign_in_accepts_only_a_json_body(
    api: TestClient, password: str, content_type: str
) -> None:
    response = api.post(
        SIGN_IN,
        content=f'{{"email": "{EDITOR}", "password": "{password}"}}',
        headers={"Content-Type": content_type},
    )

    assert response.status_code == 415
    assert "set-cookie" not in response.headers


@pytest.mark.parametrize(
    ("headers", "status"),
    [
        ({}, 201),
        ({"Origin": WEB_ORIGIN, "Sec-Fetch-Site": "same-origin"}, 201),
        ({"Origin": WEB_ORIGIN, "Sec-Fetch-Site": "cross-site"}, 201),
        ({"Origin": "http://testserver"}, 201),
        ({"Sec-Fetch-Site": "same-origin"}, 201),
        ({"Origin": OTHER_SITE}, 403),
        ({"Origin": "http://localhost:9999"}, 403),
        ({"Origin": "null"}, 403),
        ({"Sec-Fetch-Site": "cross-site"}, 403),
        ({"Sec-Fetch-Site": "same-site"}, 403),
    ],
)
def test_a_multipart_upload_is_accepted_only_from_a_trusted_origin(
    api: TestClient, password: str, headers: dict[str, str], status: int
) -> None:
    _sign_in(api, EDITOR, password)

    response = api.post(
        SOURCES, files=FILES, headers={"Idempotency-Key": "upload-key-0001", **headers}
    )

    assert response.status_code == status
    if status == 403:
        assert response.json()["code"] == "CROSS_SITE_REQUEST"
        assert api.get(SOURCES).json()["source_versions"] == []


def test_a_cross_site_post_without_a_body_is_refused(api: TestClient, password: str) -> None:
    _sign_in(api, EDITOR, password)

    response = api.post(SIGN_OUT, headers={"Origin": OTHER_SITE})

    assert response.status_code == 403
    assert response.json()["code"] == "CROSS_SITE_REQUEST"
    assert api.get(ME).status_code == 200


def test_reads_are_not_subject_to_the_cross_site_rule(api: TestClient, password: str) -> None:
    _sign_in(api, EDITOR, password)

    assert api.get(ME, headers={"Origin": OTHER_SITE}).status_code == 200


def test_sign_in_is_unavailable_under_local_development_auth(
    accounts_database_url: str, make_client: ClientFactory, password: str
) -> None:
    client = make_client(accounts_database_url)

    response = _sign_in(client, EDITOR, password)

    assert response.status_code == 503
    assert response.json()["code"] == "SIGN_IN_DISABLED"
    assert "set-cookie" not in response.headers
    assert client.get(ME).json()["email"] == LOCAL_REVIEWER.email
    assert client.post(SIGN_OUT).status_code == 204


def test_seeded_accounts_cannot_sign_in_until_a_password_is_configured(
    seeded_database_url: str, make_client: ClientFactory, password: str
) -> None:
    client = make_client(seeded_database_url, auth_mode="session")

    before = _sign_in(client, EDITOR, password)
    _run(seeded_database_url, lambda s: seed(s, account_password=password, hasher=WEAK_HASHER))
    after = _sign_in(client, EDITOR, password)

    assert (before.status_code, after.status_code) == (401, 200)


def test_seeding_accounts_is_idempotent_and_follows_a_changed_password(
    accounts_database_url: str, make_client: ClientFactory, password: str
) -> None:
    replacement = secrets.token_urlsafe(16)

    def reseed(account_password: str | None) -> bool:
        return _run(
            accounts_database_url,
            lambda s: seed(s, account_password=account_password, hasher=WEAK_HASHER),
        )

    assert reseed(password) is False
    assert reseed(None) is False, "an unset password leaves existing ones alone"
    assert reseed(replacement) is True
    client = make_client(accounts_database_url, auth_mode="session")
    assert _sign_in(client, VIEWER, password).status_code == 401
    assert _sign_in(client, VIEWER, replacement).status_code == 200


@pytest.fixture
def seed_environment(
    migrated_database_url: str, monkeypatch: pytest.MonkeyPatch
) -> Iterator[pytest.MonkeyPatch]:
    monkeypatch.setenv("DATABASE_URL", migrated_database_url)
    monkeypatch.delenv("SEED_ACCOUNT_PASSWORD", raising=False)
    get_settings.cache_clear()
    yield monkeypatch
    get_settings.cache_clear()


def test_the_seed_command_says_when_accounts_get_no_password(
    seed_environment: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seed_command.main()

    output = capsys.readouterr().out
    assert "Seeded local data." in output
    assert "SEED_ACCOUNT_PASSWORD is not set" in output


def test_the_seed_command_sets_the_configured_password_without_printing_it(
    seed_environment: pytest.MonkeyPatch,
    migrated_database_url: str,
    make_client: ClientFactory,
    password: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    seed_environment.setenv("SEED_ACCOUNT_PASSWORD", password)

    seed_command.main()

    captured = capsys.readouterr()
    assert captured.out == "Seeded local data.\n"
    assert password not in captured.out + captured.err
    client = make_client(migrated_database_url, auth_mode="session")
    assert [_sign_in(client, email, password).status_code for email in (VIEWER, EDITOR)] == [
        200,
        200,
    ]


def test_the_seed_command_refuses_a_short_password_without_printing_it(
    seed_environment: pytest.MonkeyPatch, migrated_database_url: str, password: str
) -> None:
    too_short = password[:11]
    seed_environment.setenv("SEED_ACCOUNT_PASSWORD", too_short)

    with pytest.raises(SystemExit) as stopped:
        seed_command.main()

    message = str(stopped.value.code)
    assert "SEED_ACCOUNT_PASSWORD is not usable" in message
    assert too_short not in message
    users = _run(migrated_database_url, lambda s: s.scalars(select(UserRecord)).all())
    assert users == [], "nothing is half-seeded"
