"""Open sign-up with email confirmation (ADR 0019).

The answer to a sign-up never says whether the address has an account: the owner of an existing
account is told by email instead. An account signs in only once its address is proven by the
link sent to it. Use cases return the emails to send; the caller sends them after committing.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from scopesteps.identity.application.emails import (
    EmailMessage,
    account_exists_email,
    confirmation_email,
)
from scopesteps.identity.application.limits import (
    SIGN_UP_PER_EMAIL,
    SIGN_UP_PER_IP,
    AttemptStore,
    take_attempt,
)
from scopesteps.identity.application.sessions import PasswordHasher, check_password
from scopesteps.identity.application.users import UserReader
from scopesteps.identity.client import Actor, UserId
from scopesteps.identity.domain.errors import EmailInvalidError, TokenInvalidError
from scopesteps.identity.domain.profile import normalize_profile
from scopesteps.identity.domain.tokens import (
    EMAIL_CONFIRMATION_LIFETIME,
    hash_link_token,
    new_link_token,
)
from scopesteps.identity.domain.user import User, is_valid_email, normalise_email
from scopesteps.kernel.ids import new_id


@dataclass(frozen=True)
class Links:
    """The web app's pages an email links to, from the configured `APP_BASE_URL`."""

    base_url: str

    def confirm_email(self, token: str) -> str:
        return f"{self.base_url}/verify-email/{token}"

    def invitation(self, token: str) -> str:
        return f"{self.base_url}/invite/{token}"

    def sign_in(self) -> str:
        return f"{self.base_url}/sign-in"


@dataclass(frozen=True)
class EmailToken:
    """A confirmation link's token, by its hash. It works once, until `expires_at`."""

    id: UUID
    user_id: UserId
    token_hash: str
    expires_at: datetime
    used_at: datetime | None = None


class AccountStore(UserReader, Protocol):
    def by_email(self, email: str) -> User | None:
        """`email` is normalised."""
        ...

    def add_account(self, user: User, password_hash: str) -> None:
        """Insert within the caller's transaction."""
        ...

    def reset_unverified(self, user_id: UserId, display_name: str, password_hash: str) -> None:
        """Replace the name and password of an account nobody has confirmed yet."""
        ...

    def mark_verified(self, user_id: UserId, at: datetime) -> None: ...


class EmailTokenStore(Protocol):
    def add(self, token: EmailToken) -> None: ...

    def by_hash(self, token_hash: str) -> EmailToken | None: ...

    def use(self, token: EmailToken, at: datetime) -> bool:
        """Compare-and-set: mark it used if nobody has. False, changing nothing, otherwise."""
        ...

    def discard_unused(self, user_id: UserId) -> None:
        """Delete the user's unused tokens, so only the newest link works."""
        ...


@dataclass(frozen=True)
class SignUp:
    display_name: str
    email: str
    password: str
    client_address: str


def sign_up(
    accounts: AccountStore,
    tokens: EmailTokenStore,
    attempts: AttemptStore,
    hasher: PasswordHasher,
    links: Links,
    command: SignUp,
    now: datetime,
) -> list[EmailMessage]:
    """Create an account that waits for its email to be confirmed, and return the emails to send.

    An address that already has a confirmed account gets an email saying so and nothing else. One
    nobody has confirmed is taken over by the new sign-up, since nobody has proven they own it.
    """
    name = normalize_profile(command.display_name, "", "").display_name
    email = normalise_email(command.email)
    if not is_valid_email(email):
        raise EmailInvalidError("Enter a valid email address")
    check_password(command.password)
    take_attempt(attempts, SIGN_UP_PER_IP, command.client_address, now)
    take_attempt(attempts, SIGN_UP_PER_EMAIL, email, now)
    existing = accounts.by_email(email)
    if existing is not None and existing.email_verified_at is not None:
        return [account_exists_email(to=email, sign_in_link=links.sign_in())]
    password_hash = hasher.hash(command.password)
    if existing is None:
        user = User(id=UserId(new_id()), email=email, display_name=name, created_at=now)
        accounts.add_account(user, password_hash)
    else:
        accounts.reset_unverified(existing.id, name, password_hash)
        user = existing
    return [_confirmation(tokens, links, user.id, email, name, now)]


def resend_confirmation(
    accounts: AccountStore,
    tokens: EmailTokenStore,
    attempts: AttemptStore,
    links: Links,
    *,
    email: str,
    client_address: str,
    now: datetime,
) -> list[EmailMessage]:
    """A new confirmation link for an account that has not confirmed its email; nothing for any
    other address. The answer is the same either way."""
    address = normalise_email(email)
    take_attempt(attempts, SIGN_UP_PER_IP, client_address, now)
    take_attempt(attempts, SIGN_UP_PER_EMAIL, address, now)
    user = accounts.by_email(address) if is_valid_email(address) else None
    if user is None or user.email_verified_at is not None:
        return []
    return [_confirmation(tokens, links, user.id, address, user.display_name, now)]


def confirm_email(
    accounts: AccountStore, tokens: EmailTokenStore, *, token: str, now: datetime
) -> Actor:
    """Confirm the address the link was sent to. The link works once; the caller starts a
    session for the returned actor."""
    found = tokens.by_hash(hash_link_token(token))
    if found is None or found.used_at is not None or now >= found.expires_at:
        raise TokenInvalidError
    if not tokens.use(found, now):
        raise TokenInvalidError
    user = accounts.get(found.user_id)
    if user is None:
        raise TokenInvalidError
    if user.email_verified_at is None:
        accounts.mark_verified(user.id, now)
    return Actor(user_id=user.id, display_name=user.display_name)


def _confirmation(
    tokens: EmailTokenStore,
    links: Links,
    user_id: UserId,
    email: str,
    name: str,
    now: datetime,
) -> EmailMessage:
    tokens.discard_unused(user_id)
    raw = new_link_token()
    expires_at = now + EMAIL_CONFIRMATION_LIFETIME
    tokens.add(
        EmailToken(
            id=new_id(), user_id=user_id, token_hash=hash_link_token(raw), expires_at=expires_at
        )
    )
    return confirmation_email(
        to=email, name=name, link=links.confirm_email(raw), expires_at=expires_at
    )
