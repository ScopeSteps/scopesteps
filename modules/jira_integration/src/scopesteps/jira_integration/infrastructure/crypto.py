from cryptography.fernet import Fernet, InvalidToken


class FernetTokenCipher:
    """Encrypts API tokens with the server's key (`JIRA_TOKEN_KEY`): AES with an HMAC, so a
    changed ciphertext is refused rather than decrypted into something else (ADR 0029)."""

    def __init__(self, key: str) -> None:
        self._fernet = Fernet(key.encode())

    def encrypt(self, token: str) -> bytes:
        return self._fernet.encrypt(token.encode())

    def decrypt(self, ciphertext: bytes) -> str:
        try:
            return self._fernet.decrypt(ciphertext).decode()
        except InvalidToken as error:
            # The key changed since the token was saved; the message never holds either.
            raise ValueError("the stored Jira token cannot be read with the current key") from error


def valid_key(key: str) -> bool:
    try:
        Fernet(key.encode())
    except ValueError:
        return False
    return True
