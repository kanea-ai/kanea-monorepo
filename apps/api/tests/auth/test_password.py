from __future__ import annotations

from app.infrastructure.security.password import BcryptPasswordHasher


def test_hash_then_verify_succeeds() -> None:
    hasher = BcryptPasswordHasher(rounds=4)
    hashed = hasher.hash("hunter2")
    assert hashed != "hunter2"
    assert hasher.verify("hunter2", hashed) is True


def test_verify_returns_false_for_wrong_password() -> None:
    hasher = BcryptPasswordHasher(rounds=4)
    hashed = hasher.hash("hunter2")
    assert hasher.verify("not-the-password", hashed) is False


def test_verify_returns_false_for_invalid_hash() -> None:
    hasher = BcryptPasswordHasher(rounds=4)
    assert hasher.verify("hunter2", "not-a-real-bcrypt-hash") is False
