"""One-time secrets sent in links: email confirmation and invitations (ADR 0019).

The raw token exists only in the link a person receives; the server stores its SHA-256, so a
database leak exposes no usable link.
"""

import hashlib
import secrets
from datetime import timedelta

# 256 bits from the operating system's CSPRNG, as for session tokens.
LINK_TOKEN_BYTES = 32

EMAIL_CONFIRMATION_LIFETIME = timedelta(hours=24)
INVITATION_LIFETIME = timedelta(days=7)


def new_link_token() -> str:
    return secrets.token_urlsafe(LINK_TOKEN_BYTES)


def hash_link_token(token: str) -> str:
    """A plain SHA-256 is enough because the token is random and long; it is not a password."""
    return hashlib.sha256(token.encode()).hexdigest()
