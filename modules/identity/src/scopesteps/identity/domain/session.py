import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import NewType
from uuid import UUID

from scopesteps.identity.client import UserId

SessionId = NewType("SessionId", UUID)

# 256 bits from the operating system's CSPRNG; OWASP asks for at least 64 bits of entropy.
SESSION_TOKEN_BYTES = 32

# Recording every request would turn each read into a write. A coarser last-seen time only
# makes the idle timeout up to this much more generous.
ACTIVITY_RECORDING_INTERVAL = timedelta(minutes=1)


def new_session_token() -> str:
    return secrets.token_urlsafe(SESSION_TOKEN_BYTES)


def hash_session_token(token: str) -> str:
    """The only form of a token the server stores, so a database leak exposes no live session.

    A plain SHA-256 is enough because the token is random and long; it is not a password.
    """
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class SessionPolicy:
    """How long a session lives (ADR 0007)."""

    absolute_lifetime: timedelta
    idle_timeout: timedelta


@dataclass(frozen=True)
class Session:
    id: SessionId
    user_id: UserId
    token_hash: str
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime

    def is_active(self, now: datetime, idle_timeout: timedelta) -> bool:
        return now < self.expires_at and now - self.last_seen_at < idle_timeout

    def activity_is_due(self, now: datetime) -> bool:
        return now - self.last_seen_at >= ACTIVITY_RECORDING_INTERVAL
