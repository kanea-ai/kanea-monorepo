"""Settings tripwires.

Currently pins the agent-API-key pepper guard: refuses to boot in any
non-development environment when the committed placeholder is still in
place. Better to crash on import than to silently accept a placeholder
secret in prod.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings


def test_pepper_placeholder_rejected_in_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    # Wipe any committed-default fall-throughs so the Settings constructor
    # only sees what we explicitly inject below.
    monkeypatch.delenv("AGENT_API_KEY_PEPPER", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")
    with pytest.raises(ValueError, match="placeholder"):
        Settings(_env_file=None)


def test_pepper_real_value_accepted_in_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("AGENT_API_KEY_PEPPER", "real-pepper")  # pragma: allowlist secret
    s = Settings(_env_file=None)
    assert s.agent_api_key_pepper == "real-pepper"  # pragma: allowlist secret


def test_pepper_placeholder_allowed_in_development(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_API_KEY_PEPPER", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "development")
    s = Settings(_env_file=None)
    # Boots without raising. The exact placeholder string doesn't
    # matter to the assertion — only that we got here.
    assert s.environment == "development"
