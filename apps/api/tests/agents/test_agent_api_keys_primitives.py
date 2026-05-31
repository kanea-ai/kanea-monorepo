"""Format + HMAC primitives backing ``agent_api_keys``.

These tests pin the security properties that the rest of the agent-auth
flow assumes — key shape, env-tag isolation, HMAC-vs-bare-SHA-256, etc.
"""

from __future__ import annotations

import pytest

from app.infrastructure.security.agent_api_keys import (
    KEY_FAMILY_PREFIX,
    mint,
    parse_and_hash,
)

_PEPPER = "test-pepper"


def test_mint_produces_well_formed_key() -> None:
    key = mint(env_tag="dev", pepper=_PEPPER)
    # Prefix is the family + env tag + trailing underscore.
    assert key.prefix == f"{KEY_FAMILY_PREFIX}_dev_"
    assert key.plaintext.startswith(key.prefix)
    body = key.plaintext[len(key.prefix) :]
    # 32 bytes of CSPRNG output base64url-encoded → 43 chars.
    assert len(body) == 43
    # last4 is the trailing slice of the body, NOT the prefix.
    assert key.last4 == body[-4:]
    # Hex SHA-256 digest is 64 chars.
    assert len(key.secret_hash) == 64
    int(key.secret_hash, 16)  # parses as hex


def test_two_mints_yield_distinct_keys_and_hashes() -> None:
    a = mint(env_tag="dev", pepper=_PEPPER)
    b = mint(env_tag="dev", pepper=_PEPPER)
    assert a.plaintext != b.plaintext
    assert a.secret_hash != b.secret_hash


def test_parse_and_hash_roundtrip_matches_mint() -> None:
    minted = mint(env_tag="dev", pepper=_PEPPER)
    looked_up = parse_and_hash(minted.plaintext, expected_env_tag="dev", pepper=_PEPPER)
    assert looked_up == minted.secret_hash


def test_parse_rejects_wrong_env_tag() -> None:
    minted = mint(env_tag="dev", pepper=_PEPPER)
    assert parse_and_hash(minted.plaintext, expected_env_tag="live", pepper=_PEPPER) is None


def test_parse_rejects_wrong_family_prefix() -> None:
    assert parse_and_hash("knm_dev_abc", expected_env_tag="dev", pepper=_PEPPER) is None


def test_parse_rejects_malformed() -> None:
    for bad in ["", "kna_", "kna__abc", "nope", "kna_dev_"]:
        assert parse_and_hash(bad, expected_env_tag="dev", pepper=_PEPPER) is None


@pytest.mark.parametrize("pepper_a, pepper_b", [("a", "b"), ("x", "X")])
def test_pepper_change_invalidates_hash(pepper_a: str, pepper_b: str) -> None:
    """The HMAC pepper is the actual access control beyond the body's
    entropy. Anyone who steals the DB but not the pepper cannot
    pre-compute a hash table of guessed bodies."""
    minted = mint(env_tag="dev", pepper=pepper_a)
    assert (
        parse_and_hash(minted.plaintext, expected_env_tag="dev", pepper=pepper_b)
        != minted.secret_hash
    )


def test_malformed_and_cross_env_short_circuit_before_hmac(monkeypatch) -> None:
    """Security property: a flood of garbage keys (malformed or wrong
    env-tag) MUST NOT reach the HMAC compute path — otherwise an
    unauthenticated attacker could weaponise the exchange endpoint as
    a CPU-exhaustion vector. We pin this by patching the HMAC helper
    to record any call and asserting it stays untouched on rejected
    inputs."""
    from app.infrastructure.security import agent_api_keys as mod

    calls: list[tuple[str, str]] = []

    def _spy(body: str, pepper: str) -> str:
        calls.append((body, pepper))
        return "x" * 64

    monkeypatch.setattr(mod, "_hmac_hex", _spy)

    # Malformed (no underscores).
    assert mod.parse_and_hash("not-a-key", expected_env_tag="dev", pepper="p") is None
    # Wrong family prefix.
    assert mod.parse_and_hash("knm_dev_abc", expected_env_tag="dev", pepper="p") is None
    # Wrong env-tag.
    assert mod.parse_and_hash("kna_live_abc", expected_env_tag="dev", pepper="p") is None
    # Empty body.
    assert mod.parse_and_hash("kna_dev_", expected_env_tag="dev", pepper="p") is None

    assert calls == [], "HMAC must NOT run for rejected keys"

    # Sanity: a well-formed key DOES reach the HMAC path.
    assert mod.parse_and_hash("kna_dev_real-body", expected_env_tag="dev", pepper="p") is not None
    assert calls == [("real-body", "p")]
