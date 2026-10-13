import secrets

import pytest
from argon2 import PasswordHasher

from scopesteps.identity.infrastructure.passwords import Argon2PasswordHasher

# The smallest parameters Argon2 accepts: these tests are about behaviour, not strength.
WEAK = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)


@pytest.fixture
def password() -> str:
    return secrets.token_urlsafe(16)


def test_default_hashes_are_salted_argon2id(password: str) -> None:
    hasher = Argon2PasswordHasher()

    first, second = hasher.hash(password), hasher.hash(password)

    assert first.startswith("$argon2id$")
    assert first != second, "each hash has its own salt"
    assert password not in first
    assert hasher.verify(first, password)
    assert not hasher.needs_rehash(first)


def test_verify_refuses_a_wrong_password_a_missing_hash_and_a_malformed_hash(
    password: str,
) -> None:
    hasher = Argon2PasswordHasher(WEAK)
    stored = hasher.hash(password)

    assert not hasher.verify(stored, password + "x")
    assert not hasher.verify(None, password)
    assert not hasher.verify("not-a-hash", password)


def test_a_hash_made_with_other_parameters_still_verifies_and_asks_for_a_rehash(
    password: str,
) -> None:
    old = Argon2PasswordHasher(WEAK).hash(password)
    current = Argon2PasswordHasher(PasswordHasher(time_cost=2, memory_cost=16, parallelism=1))

    assert current.verify(old, password)
    assert current.needs_rehash(old)
