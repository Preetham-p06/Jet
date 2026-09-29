"""Password hashing with argon2id (pwdlib)."""

from __future__ import annotations

from functools import lru_cache

from pwdlib import PasswordHash

MIN_PASSWORD_LENGTH = 10


@lru_cache
def _hasher() -> PasswordHash:
    return PasswordHash.recommended()


@lru_cache
def _dummy_hash() -> str:
    return _hasher().hash("jetstream-timing-equalizer")


def hash_password(password: str) -> str:
    return _hasher().hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """Check a password; with no hash (unknown account) burn equivalent time and fail.

    Running a real verification against a dummy hash keeps the response time of
    "no such user" indistinguishable from "wrong password".
    """
    if password_hash is None:
        _hasher().verify(password, _dummy_hash())
        return False
    return _hasher().verify(password, password_hash)


def needs_rehash(password_hash: str) -> bool:
    return _hasher().current_hasher.check_needs_rehash(password_hash)
