import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError


class Argon2PasswordHasher:
    """Argon2id with the library's recommended parameters (ADR 0007).

    Each hash carries its own salt and parameters, so raising the defaults later only needs
    `needs_rehash` to be honoured at sign-in.
    """

    def __init__(self, hasher: PasswordHasher | None = None) -> None:
        self._hasher = hasher or PasswordHasher()
        # A hash of a discarded random value, with the current parameters: verifying against it
        # costs what a real verification costs and can never succeed.
        self._dummy_hash = self._hasher.hash(secrets.token_urlsafe())

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, password_hash: str | None, password: str) -> bool:
        try:
            self._hasher.verify(password_hash or self._dummy_hash, password)
        except VerificationError, InvalidHashError:
            return False
        return password_hash is not None

    def needs_rehash(self, password_hash: str) -> bool:
        return self._hasher.check_needs_rehash(password_hash)
