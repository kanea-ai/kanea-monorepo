from __future__ import annotations

import os

# Env defaults must be set BEFORE pytest (and transitively, app.core.config)
# is imported — otherwise Settings() picks up the dev DSN. The noqa on the
# pytest import below is for ruff's E402 since it sits intentionally
# after these setdefault calls.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "test-secret-do-not-use-in-prod")


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _bypass_suspension_gate_by_default():
    """Auto-applied fixture that skips the workspace-suspension lookup
    in ``get_current_principal`` for every test by default.

    The suspension gate added in migration 0020 issues a per-request
    DB lookup so a flipped ``is_suspended`` flag invalidates a JWT on
    the very next call. Most of the existing test suite mocks the
    service layer and forges a JWT directly — they don't seed a
    member row, so the gate's DB lookup would 401 every request and
    break tests that pre-date the gate.

    This fixture rebinds ``get_current_principal`` to the JWT-only
    decoder ``_decode_principal``, restoring the pre-gate behaviour.
    Tests that explicitly want to exercise the gate
    (tests/suspension/...) clear the override in their own fixture.
    """
    from app.api.deps import _decode_principal, get_current_principal
    from app.main import app

    app.dependency_overrides[get_current_principal] = _decode_principal
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_current_principal, None)
