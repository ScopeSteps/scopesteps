"""Attempt limits that stop bots and abuse (ADR 0019).

Attempts are counted per bucket and key in a rolling window and stored, so a limit holds across
API processes and restarts. Keys are hashed before they are stored: an email address or an IP
never sits in the table.
"""

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal, Protocol

from scopesteps.identity.domain.errors import TooManyAttemptsError

Bucket = Literal["sign_up_ip", "sign_up_email", "invitation_email"]


@dataclass(frozen=True)
class Limit:
    bucket: Bucket
    attempts: int
    window: timedelta


HOUR = timedelta(hours=1)
SIGN_UP_PER_IP = Limit("sign_up_ip", 5, HOUR)
"""Sign-ups and confirmation resends from one address, so a bot cannot sweep many emails."""
SIGN_UP_PER_EMAIL = Limit("sign_up_email", 3, HOUR)
"""Sign-ups and resends for one email, so nobody can flood one inbox."""
INVITATION_EMAILS_PER_APPROVER = Limit("invitation_email", 20, HOUR)


class AttemptStore(Protocol):
    def count(self, bucket: Bucket, key_hash: str, since: datetime) -> int: ...

    def add(self, bucket: Bucket, key_hash: str, at: datetime) -> None:
        """Insert within the caller's transaction."""
        ...


def take_attempt(store: AttemptStore, limit: Limit, key: str, now: datetime) -> None:
    """Count one attempt, or refuse it with 429 `RATE_LIMITED` once the window holds the limit."""
    key_hash = hashlib.sha256(f"{limit.bucket}:{key}".encode()).hexdigest()
    if store.count(limit.bucket, key_hash, now - limit.window) >= limit.attempts:
        raise TooManyAttemptsError
    store.add(limit.bucket, key_hash, now)
