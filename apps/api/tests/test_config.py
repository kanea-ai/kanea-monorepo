"""Settings tripwires — unified `_check_required_secrets_in_prod`.

Folds the standalone `_check_pepper_set_in_prod` (introduced in
PRs #39-#41) into a single rule that also enforces ``jwt_secret`` per
issue #42. Adding a new required-in-prod secret should be a one-line
edit to the ``_REQUIRED_IN_PROD_PLACEHOLDERS`` registry plus a single
test that follows the pattern below.

The tests live in two halves:

* ``Environment`` field validation (pydantic-level, runs BEFORE the
  model_validator). Pins the ordering requirement: a broken
  ENVIRONMENT must surface as the environment field's own error and
  never cascade into a misleading list of "secret X is the placeholder"
  errors that are really downstream of environment never being set.

* The model_validator (when ``environment != "development"``). Pins
  the unified rule for both secrets and the aggregated-error shape.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import (
    _DEV_JWT_SECRET_PLACEHOLDER,
    _DEV_PEPPER_PLACEHOLDER,
    Settings,
)

# ---------- Step 1: environment field is itself fail-loud ----------


def test_environment_required(monkeypatch: pytest.MonkeyPatch) -> None:
    """No ENVIRONMENT supplied → pydantic raises a field-required error
    specifically on `environment`. Closes the root disease where a
    prod deploy that forgets to set ENVIRONMENT silently disarms every
    downstream validator (the original PR-#41 gap class)."""
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)
    locs = [e["loc"] for e in exc.value.errors()]
    assert ("environment",) in locs


def test_environment_rejects_typo(monkeypatch: pytest.MonkeyPatch) -> None:
    """An ENVIRONMENT typo (e.g. ``prod-typo``) surfaces as the
    environment field's own error — NOT as a misleading cascade of
    "secret X is the placeholder" errors that are really symptoms of
    environment-never-set. Pins the ordering requirement: pydantic's
    Literal validation runs BEFORE the model_validator, so the only
    error a caller sees is the one that's actually wrong."""
    monkeypatch.setenv("ENVIRONMENT", "prod-typo")
    monkeypatch.setenv("JWT_SECRET", "real-jwt")  # pragma: allowlist secret
    monkeypatch.setenv("AGENT_API_KEY_PEPPER", "real-pepper")  # pragma: allowlist secret
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)
    locs = [e["loc"] for e in exc.value.errors()]
    assert ("environment",) in locs
    # No downstream cascade — the placeholder check did NOT fire.
    msg = str(exc.value)
    assert "jwt_secret" not in msg
    assert "agent_api_key_pepper" not in msg


# ---------- Step 2: required-in-prod secrets are unified ----------


def test_pepper_placeholder_rejected_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verbatim equivalent of the standalone test PRs #39-#41 pinned.
    Preserved unchanged so the fold doesn't weaken the pepper's
    protection — same trigger (environment != "development" AND
    agent_api_key_pepper == placeholder), same fail-loud at import."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("JWT_SECRET", "real-jwt")  # pragma: allowlist secret
    monkeypatch.delenv("AGENT_API_KEY_PEPPER", raising=False)
    with pytest.raises(ValueError, match="agent_api_key_pepper"):
        Settings(_env_file=None)


def test_jwt_secret_placeholder_rejected_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Issue #42's symmetric test: prod refuses the committed JWT
    secret placeholder. Without this, the field default
    ``change-me-in-production`` silently signs every JWT in prod."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("AGENT_API_KEY_PEPPER", "real-pepper")  # pragma: allowlist secret
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(ValueError, match="jwt_secret"):
        Settings(_env_file=None)


def test_both_placeholders_aggregated_in_one_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fresh deploy that forgot BOTH secrets sees both field names
    in a single error, not three deploys-worth of fix-one-at-a-time.
    Also pins the security invariant: the error message must name
    fields, never values — no placeholder strings (and by extension
    no real values, since both go through the same code path) ever
    leak through the error."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.delenv("AGENT_API_KEY_PEPPER", raising=False)
    with pytest.raises(ValueError) as exc:
        Settings(_env_file=None)
    msg = str(exc.value)
    # Field names listed.
    assert "jwt_secret" in msg
    assert "agent_api_key_pepper" in msg
    # Values NOT leaked.
    assert _DEV_JWT_SECRET_PLACEHOLDER not in msg
    assert _DEV_PEPPER_PLACEHOLDER not in msg


def test_staging_environment_same_protection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Staging gets identical enforcement to production. ``staging``
    is a real deploy with real users, not a dev sandbox; it should
    never silently accept a placeholder secret either."""
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.setenv("AGENT_API_KEY_PEPPER", "real-pepper")  # pragma: allowlist secret
    with pytest.raises(ValueError, match="jwt_secret"):
        Settings(_env_file=None)


def test_development_allows_placeholders(monkeypatch: pytest.MonkeyPatch) -> None:
    """Local dev / CI continues to boot with the committed
    placeholders for both jwt_secret and agent_api_key_pepper.
    Without this, every developer's local environment + every CI
    test run would break on the first import of ``app.core.config``."""
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.delenv("AGENT_API_KEY_PEPPER", raising=False)
    s = Settings(_env_file=None)
    assert s.environment == "development"
    assert s.jwt_secret == _DEV_JWT_SECRET_PLACEHOLDER
    assert s.agent_api_key_pepper == _DEV_PEPPER_PLACEHOLDER


def test_real_values_pass_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sanity: a fully-provisioned prod environment boots cleanly."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("JWT_SECRET", "real-jwt")  # pragma: allowlist secret
    monkeypatch.setenv("AGENT_API_KEY_PEPPER", "real-pepper")  # pragma: allowlist secret
    s = Settings(_env_file=None)
    assert s.environment == "production"
    assert s.jwt_secret == "real-jwt"  # pragma: allowlist secret
    assert s.agent_api_key_pepper == "real-pepper"  # pragma: allowlist secret
