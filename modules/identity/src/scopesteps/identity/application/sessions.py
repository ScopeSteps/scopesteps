"""Password sign-in and server-side sessions (ADR 0007)."""

import hmac
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from scopesteps.identity.application.users import UserReader
from scopesteps.identity.client import Actor, UserId
from scopesteps.identity.domain.errors import (
    EmailNotVerifiedError,
    InvalidCredentialsError,
    SessionRequiredError,
)
from scopesteps.identity.domain.session import (
    Session,
    SessionId,
    SessionPolicy,
    hash_session_token,
    new_session_token,
)
from scopesteps.identity.domain.user import (
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    Credentials,
    normalise_email,
)
from scopesteps.kernel.errors import InvalidInputError, NotFoundError
from scopesteps.kernel.ids import new_id


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, password_hash: str | None, password: str) -> bool:
        """Whether the password matches. Never raises for a wrong or malformed hash.

        With no hash it does the same work against a dummy and returns False, so a caller cannot
        tell an unknown account from a wrong password by timing.
        """
        ...

    def needs_rehash(self, password_hash: str) -> bool: ...


class CredentialStore(Protocol):
    def credentials_for_email(self, email: str) -> Credentials | None:
        """`email` is already normalised."""
        ...

    def credentials(self, user_id: UserId) -> Credentials | None: ...

    def set_password_hash(self, user_id: UserId, password_hash: str) -> None: ...


class SessionStore(Protocol):
    def add(self, session: Session) -> None: ...

    def get_by_token_hash(self, token_hash: str) -> Session | None: ...

    def record_activity(self, session_id: SessionId, seen_at: datetime) -> None: ...

    def delete_by_token_hash(self, token_hash: str) -> None: ...

    def delete_expired(self, now: datetime) -> None: ...


@dataclass(frozen=True)
class SignedIn:
    """`token` is the only copy of the session secret; it goes to the client and nowhere else."""

    token: str
    session: Session
    actor: Actor


def sign_in(
    users: UserReader,
    credential_store: CredentialStore,
    sessions: SessionStore,
    hasher: PasswordHasher,
    policy: SessionPolicy,
    *,
    email: str,
    password: str,
    presented_token: str | None,
    now: datetime,
) -> SignedIn:
    """Start a new session. Every failure raises the same `InvalidCredentialsError`, except that
    an account whose email is not confirmed yet gets `EmailNotVerifiedError` once its password
    matched, which tells a guesser nothing.

    The session a client already holds is ended and never reused, so a token planted before
    sign-in is worthless afterwards.
    """
    credentials = credential_store.credentials_for_email(normalise_email(email))
    password_hash = None if credentials is None else credentials.password_hash
    # Verified even when there is no account or no hash, so both failures take the same time.
    verified = hasher.verify(password_hash, password)
    if credentials is None or not verified:
        raise InvalidCredentialsError
    user = users.get(credentials.user_id)
    if user is None:
        raise InvalidCredentialsError
    if not credentials.email_verified:
        raise EmailNotVerifiedError
    if password_hash is not None and hasher.needs_rehash(password_hash):
        credential_store.set_password_hash(user.id, hasher.hash(password))
    return start_session(
        sessions,
        policy,
        Actor(user_id=user.id, display_name=user.display_name),
        presented_token=presented_token,
        now=now,
    )


def start_session(
    sessions: SessionStore,
    policy: SessionPolicy,
    actor: Actor,
    *,
    presented_token: str | None,
    now: datetime,
) -> SignedIn:
    """A new session for `actor`, whose identity the caller has proven. Any session the client
    already holds is ended first."""
    if presented_token:
        sessions.delete_by_token_hash(hash_session_token(presented_token))
    sessions.delete_expired(now)
    token = new_session_token()
    session = Session(
        id=SessionId(new_id()),
        user_id=actor.user_id,
        token_hash=hash_session_token(token),
        created_at=now,
        last_seen_at=now,
        expires_at=now + policy.absolute_lifetime,
    )
    sessions.add(session)
    return SignedIn(token=token, session=session, actor=actor)


def authenticate_session(
    users: UserReader,
    sessions: SessionStore,
    policy: SessionPolicy,
    *,
    token: str | None,
    now: datetime,
) -> Actor:
    if not token:
        raise SessionRequiredError
    token_hash = hash_session_token(token)
    session = sessions.get_by_token_hash(token_hash)
    if (
        session is None
        or not hmac.compare_digest(session.token_hash, token_hash)
        or not session.is_active(now, policy.idle_timeout)
    ):
        raise SessionRequiredError
    user = users.get(session.user_id)
    if user is None:
        raise SessionRequiredError
    if session.activity_is_due(now):
        sessions.record_activity(session.id, now)
    return Actor(user_id=user.id, display_name=user.display_name)


def sign_out(sessions: SessionStore, *, token: str | None) -> None:
    """End the presented session on the server. Signing out twice, or with no session, is fine."""
    if token:
        sessions.delete_by_token_hash(hash_session_token(token))


def check_password(password: str) -> None:
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        raise InvalidInputError(
            f"A password must be {MIN_PASSWORD_LENGTH} to {MAX_PASSWORD_LENGTH} characters long",
            details={"min_length": MIN_PASSWORD_LENGTH, "max_length": MAX_PASSWORD_LENGTH},
        )


def ensure_password(
    credential_store: CredentialStore, hasher: PasswordHasher, user_id: UserId, password: str
) -> bool:
    """Make `password` the user's password. Returns whether the stored hash changed."""
    check_password(password)
    credentials = credential_store.credentials(user_id)
    if credentials is None:
        raise NotFoundError("User not found")
    current = credentials.password_hash
    if (
        current is not None
        and hasher.verify(current, password)
        and not hasher.needs_rehash(current)
    ):
        return False
    credential_store.set_password_hash(user_id, hasher.hash(password))
    return True
