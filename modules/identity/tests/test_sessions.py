import secrets
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from scopesteps.identity.application.sessions import (
    authenticate_session,
    ensure_password,
    sign_in,
    sign_out,
)
from scopesteps.identity.client import UserId
from scopesteps.identity.domain.errors import InvalidCredentialsError, SessionRequiredError
from scopesteps.identity.domain.session import (
    Session,
    SessionId,
    SessionPolicy,
    hash_session_token,
)
from scopesteps.identity.domain.user import Credentials, Membership, User
from scopesteps.kernel.errors import InvalidInputError

NOW = datetime(2026, 10, 13, 9, 0, tzinfo=UTC)
POLICY = SessionPolicy(absolute_lifetime=timedelta(hours=12), idle_timeout=timedelta(hours=2))
EDITOR = User(
    id=UserId(UUID("019a3a5e-0000-7000-8000-0000000000b1")),
    email="editor@scopesteps.local",
    display_name="Sample Editor",
    created_at=NOW,
    email_verified_at=NOW,
)
OLD_SCHEME = "old"
CURRENT_SCHEME = "current"


class FakeHasher:
    """Reversible on purpose: tests need to see which scheme and password a hash holds."""

    def __init__(self) -> None:
        self.verified: list[str | None] = []

    def hash(self, password: str) -> str:
        return f"{CURRENT_SCHEME}:{password}"

    def verify(self, password_hash: str | None, password: str) -> bool:
        self.verified.append(password_hash)
        return password_hash is not None and password_hash.split(":", 1)[1] == password

    def needs_rehash(self, password_hash: str) -> bool:
        return not password_hash.startswith(f"{CURRENT_SCHEME}:")


class InMemoryAccounts:
    def __init__(self, *users: User) -> None:
        self.users = {user.id: user for user in users}
        self.password_hashes: dict[UserId, str] = {}

    def get(self, user_id: UserId) -> User | None:
        return self.users.get(user_id)

    def memberships(self, user_id: UserId) -> list[Membership]:
        return []

    def credentials_for_email(self, email: str) -> Credentials | None:
        for user in self.users.values():
            if user.email == email:
                return self.credentials(user.id)
        return None

    def credentials(self, user_id: UserId) -> Credentials | None:
        if user_id not in self.users:
            return None
        return Credentials(
            user_id=user_id,
            password_hash=self.password_hashes.get(user_id),
            email_verified=self.users[user_id].email_verified_at is not None,
        )

    def set_password_hash(self, user_id: UserId, password_hash: str) -> None:
        self.password_hashes[user_id] = password_hash


class InMemorySessions:
    def __init__(self) -> None:
        self.sessions: dict[SessionId, Session] = {}

    def add(self, session: Session) -> None:
        self.sessions[session.id] = session

    def get_by_token_hash(self, token_hash: str) -> Session | None:
        for session in self.sessions.values():
            if session.token_hash == token_hash:
                return session
        return None

    def record_activity(self, session_id: SessionId, seen_at: datetime) -> None:
        self.sessions[session_id] = replace(self.sessions[session_id], last_seen_at=seen_at)

    def delete_by_token_hash(self, token_hash: str) -> None:
        self.sessions = {k: s for k, s in self.sessions.items() if s.token_hash != token_hash}

    def delete_expired(self, now: datetime) -> None:
        self.sessions = {k: s for k, s in self.sessions.items() if s.expires_at > now}


class World:
    def __init__(self) -> None:
        self.password = secrets.token_urlsafe(16)
        self.accounts = InMemoryAccounts(EDITOR)
        self.sessions = InMemorySessions()
        self.hasher = FakeHasher()
        self.accounts.password_hashes[EDITOR.id] = self.hasher.hash(self.password)

    def sign_in(
        self,
        *,
        email: str = EDITOR.email,
        password: str | None = None,
        presented_token: str | None = None,
        now: datetime = NOW,
    ) -> str:
        return sign_in(
            self.accounts,
            self.accounts,
            self.sessions,
            self.hasher,
            POLICY,
            email=email,
            password=self.password if password is None else password,
            presented_token=presented_token,
            now=now,
        ).token

    def authenticate(self, token: str | None, now: datetime) -> UserId:
        return authenticate_session(
            self.accounts, self.sessions, POLICY, token=token, now=now
        ).user_id


@pytest.fixture
def world() -> World:
    return World()


def test_sign_in_starts_a_session_that_authenticates_its_user(world: World) -> None:
    token = world.sign_in()

    assert world.authenticate(token, NOW + timedelta(minutes=5)) == EDITOR.id


def test_only_a_hash_of_the_session_token_is_stored(world: World) -> None:
    token = world.sign_in()

    (stored,) = world.sessions.sessions.values()
    assert stored.token_hash == hash_session_token(token)
    assert token not in repr(stored)


@pytest.mark.parametrize("email", ["EDITOR@ScopeSteps.local", "  editor@scopesteps.local "])
def test_email_is_matched_case_insensitively(world: World, email: str) -> None:
    assert world.authenticate(world.sign_in(email=email), NOW) == EDITOR.id


@pytest.mark.parametrize(
    ("email", "password"),
    [
        (EDITOR.email, "not-the-password"),
        ("nobody@scopesteps.local", None),
        ("nobody@scopesteps.local", "not-the-password"),
    ],
)
def test_wrong_password_and_unknown_email_fail_identically(
    world: World, email: str, password: str | None
) -> None:
    with pytest.raises(InvalidCredentialsError) as failure:
        world.sign_in(email=email, password=password)

    assert (failure.value.code, failure.value.message, failure.value.details) == (
        "INVALID_CREDENTIALS",
        "Email or password is incorrect",
        {},
    )
    assert len(world.hasher.verified) == 1, "the hasher does its work for every attempt"
    assert world.sessions.sessions == {}


def test_an_account_without_a_password_cannot_sign_in(world: World) -> None:
    del world.accounts.password_hashes[EDITOR.id]

    with pytest.raises(InvalidCredentialsError):
        world.sign_in()

    assert world.hasher.verified == [None]


def test_a_hash_made_with_old_parameters_is_replaced_at_sign_in(world: World) -> None:
    world.accounts.password_hashes[EDITOR.id] = f"{OLD_SCHEME}:{world.password}"

    world.sign_in()

    assert world.accounts.password_hashes[EDITOR.id] == f"{CURRENT_SCHEME}:{world.password}"


def test_a_failed_sign_in_never_rehashes(world: World) -> None:
    world.accounts.password_hashes[EDITOR.id] = f"{OLD_SCHEME}:{world.password}"

    with pytest.raises(InvalidCredentialsError):
        world.sign_in(password=world.password + "x")

    assert world.accounts.password_hashes[EDITOR.id] == f"{OLD_SCHEME}:{world.password}"


def test_signing_in_again_ends_the_session_the_client_presented(world: World) -> None:
    first = world.sign_in()

    second = world.sign_in(presented_token=first)

    assert second != first
    assert world.authenticate(second, NOW) == EDITOR.id
    with pytest.raises(SessionRequiredError):
        world.authenticate(first, NOW)


def test_a_token_chosen_by_the_client_never_becomes_a_session(world: World) -> None:
    planted = "token-planted-before-sign-in"

    issued = world.sign_in(presented_token=planted)

    assert issued != planted
    with pytest.raises(SessionRequiredError):
        world.authenticate(planted, NOW)


@pytest.mark.parametrize("token", [None, "", "unknown-token"])
def test_a_missing_or_unknown_token_is_not_a_session(world: World, token: str | None) -> None:
    world.sign_in()

    with pytest.raises(SessionRequiredError):
        world.authenticate(token, NOW)


def test_a_session_ends_at_its_absolute_lifetime_even_when_active(world: World) -> None:
    token = world.sign_in()
    for hours in range(1, 12):
        world.authenticate(token, NOW + timedelta(hours=hours))

    with pytest.raises(SessionRequiredError):
        world.authenticate(token, NOW + POLICY.absolute_lifetime)


def test_a_session_ends_after_the_idle_timeout(world: World) -> None:
    token = world.sign_in()
    world.authenticate(token, NOW + timedelta(minutes=30))

    world.authenticate(token, NOW + timedelta(minutes=149))
    with pytest.raises(SessionRequiredError):
        world.authenticate(token, NOW + timedelta(minutes=149) + POLICY.idle_timeout)


def test_activity_is_recorded_at_most_once_a_minute(world: World) -> None:
    token = world.sign_in()

    world.authenticate(token, NOW + timedelta(seconds=59))
    (after_a_quick_request,) = world.sessions.sessions.values()
    world.authenticate(token, NOW + timedelta(seconds=60))
    (after_a_minute,) = world.sessions.sessions.values()

    assert after_a_quick_request.last_seen_at == NOW
    assert after_a_minute.last_seen_at == NOW + timedelta(seconds=60)


def test_a_session_of_a_deleted_user_is_refused(world: World) -> None:
    token = world.sign_in()
    del world.accounts.users[EDITOR.id]

    with pytest.raises(SessionRequiredError):
        world.authenticate(token, NOW)


def test_sign_out_ends_the_session_and_can_be_repeated(world: World) -> None:
    token = world.sign_in()

    sign_out(world.sessions, token=token)
    sign_out(world.sessions, token=token)
    sign_out(world.sessions, token=None)

    assert world.sessions.sessions == {}
    with pytest.raises(SessionRequiredError):
        world.authenticate(token, NOW)


def test_sign_in_clears_out_expired_sessions(world: World) -> None:
    world.sign_in()

    world.sign_in(now=NOW + POLICY.absolute_lifetime)

    assert len(world.sessions.sessions) == 1


def test_ensure_password_changes_the_hash_only_when_needed(world: World) -> None:
    replacement = secrets.token_urlsafe(16)

    unchanged = ensure_password(world.accounts, world.hasher, EDITOR.id, world.password)
    changed = ensure_password(world.accounts, world.hasher, EDITOR.id, replacement)

    assert (unchanged, changed) == (False, True)
    assert world.accounts.password_hashes[EDITOR.id] == world.hasher.hash(replacement)


@pytest.mark.parametrize("length", [0, 11, 1025])
def test_ensure_password_rejects_a_password_of_the_wrong_length(world: World, length: int) -> None:
    with pytest.raises(InvalidInputError):
        ensure_password(world.accounts, world.hasher, EDITOR.id, "p" * length)
