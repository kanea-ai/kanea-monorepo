from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_auth_service
from app.application.auth.schemas import LoginResponse, TokenResponse
from app.domain.exceptions import (
    AuthenticationError,
    EmailAlreadyExistsError,
    WorkspaceNameConflictError,
)
from app.main import app


@pytest.fixture
def auth_service() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def client(auth_service: AsyncMock) -> Iterator[TestClient]:
    app.dependency_overrides[get_auth_service] = lambda: auth_service
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_login_returns_token(client: TestClient, auth_service: AsyncMock) -> None:
    auth_service.login.return_value = LoginResponse(
        requires_selection=False, access_token="jwt", expires_in=3600
    )

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "alice@kanea.ai", "password": "hunter2"},  # pragma: allowlist secret
    )

    assert response.status_code == 200
    body = response.json()
    assert body["requires_selection"] is False
    assert body["access_token"] == "jwt"
    assert body["expires_in"] == 3600
    auth_service.login.assert_awaited_once()


def test_login_multi_workspace_returns_selection(
    client: TestClient, auth_service: AsyncMock
) -> None:
    auth_service.login.return_value = LoginResponse(
        requires_selection=True,
        selection_token="sel.jwt",
        workspaces=[],  # populated by the real service
    )

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "alice@kanea.ai", "password": "hunter2"},  # pragma: allowlist secret
    )

    assert response.status_code == 200
    body = response.json()
    assert body["requires_selection"] is True
    assert body["selection_token"] == "sel.jwt"
    assert body["access_token"] is None


def test_login_invalid_credentials_returns_401(client: TestClient, auth_service: AsyncMock) -> None:
    auth_service.login.side_effect = AuthenticationError("invalid email or password")

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "alice@kanea.ai", "password": "hunter2"},  # pragma: allowlist secret
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "invalid email or password"
    assert response.headers["www-authenticate"] == "Bearer"


def test_login_validation_error_returns_422(client: TestClient) -> None:
    response = client.post("/api/v1/auth/login", json={"email": "not-an-email", "password": ""})
    assert response.status_code == 422


def test_agent_token_returns_token(client: TestClient, auth_service: AsyncMock) -> None:
    auth_service.issue_agent_token.return_value = TokenResponse(
        access_token="agent-jwt", expires_in=900
    )

    response = client.post(
        "/api/v1/auth/agent-token", json={"agent_id": str(uuid4()), "secret": "s3cret"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"] == "agent-jwt"
    assert body["expires_in"] == 900
    auth_service.issue_agent_token.assert_awaited_once()


def test_agent_token_invalid_returns_401(client: TestClient, auth_service: AsyncMock) -> None:
    auth_service.issue_agent_token.side_effect = AuthenticationError("invalid agent credentials")

    response = client.post(
        "/api/v1/auth/agent-token", json={"agent_id": str(uuid4()), "secret": "x"}
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "invalid agent credentials"


def test_agent_token_validation_error_returns_422(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/agent-token", json={"agent_id": "not-a-uuid", "secret": "s"}
    )
    assert response.status_code == 422


# ---------- register ----------


_VALID_REGISTER = {
    "email": "alice@kanea.ai",
    "password": "hunter2hunter2",  # pragma: allowlist secret
    "full_name": "Alice",
    "workspace_name": "Acme",
}


def test_register_returns_201_with_token(client: TestClient, auth_service: AsyncMock) -> None:
    auth_service.register.return_value = TokenResponse(access_token="new-jwt", expires_in=3600)

    response = client.post("/api/v1/auth/register", json=_VALID_REGISTER)

    assert response.status_code == 201
    assert response.json() == {
        "access_token": "new-jwt",
        "token_type": "bearer",
        "expires_in": 3600,
    }
    auth_service.register.assert_awaited_once()


def test_register_duplicate_email_returns_409(client: TestClient, auth_service: AsyncMock) -> None:
    auth_service.register.side_effect = EmailAlreadyExistsError(
        "an account with this email already exists"
    )

    response = client.post("/api/v1/auth/register", json=_VALID_REGISTER)

    assert response.status_code == 409
    assert response.json()["detail"] == "an account with this email already exists"


def test_register_validation_error_returns_422(client: TestClient) -> None:
    # Password under min_length=8 must be rejected before the service is hit.
    bad = {**_VALID_REGISTER, "password": "short"}  # pragma: allowlist secret
    response = client.post("/api/v1/auth/register", json=bad)
    assert response.status_code == 422


# ---------- complete-oauth-onboarding ----------


def test_complete_onboarding_returns_token(client: TestClient, auth_service: AsyncMock) -> None:
    auth_service.complete_oauth_onboarding.return_value = TokenResponse(
        access_token="real.jwt", expires_in=3600
    )
    response = client.post(
        "/api/v1/auth/complete-oauth-onboarding",
        json={"onboarding_token": "onboarding.jwt", "workspace_name": "Acme"},
    )
    assert response.status_code == 201
    assert response.json()["access_token"] == "real.jwt"
    auth_service.complete_oauth_onboarding.assert_awaited_once()


def test_complete_onboarding_invalid_token_returns_401(
    client: TestClient, auth_service: AsyncMock
) -> None:
    auth_service.complete_oauth_onboarding.side_effect = AuthenticationError(
        "invalid or expired onboarding token"
    )
    response = client.post(
        "/api/v1/auth/complete-oauth-onboarding",
        json={"onboarding_token": "bad.jwt", "workspace_name": "Acme"},
    )
    assert response.status_code == 401
    assert "expired" in response.json()["detail"]


def test_complete_onboarding_name_conflict_returns_409(
    client: TestClient, auth_service: AsyncMock
) -> None:
    auth_service.complete_oauth_onboarding.side_effect = WorkspaceNameConflictError(
        "a workspace with that name already exists"
    )
    response = client.post(
        "/api/v1/auth/complete-oauth-onboarding",
        json={"onboarding_token": "onboarding.jwt", "workspace_name": "Taken"},
    )
    assert response.status_code == 409


def test_complete_onboarding_validation_error_returns_422(client: TestClient) -> None:
    """Empty workspace_name is rejected at the schema layer, never
    reaches the service."""
    response = client.post(
        "/api/v1/auth/complete-oauth-onboarding",
        json={"onboarding_token": "onboarding.jwt", "workspace_name": ""},
    )
    assert response.status_code == 422
