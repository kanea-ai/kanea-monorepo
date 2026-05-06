from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_auth_service
from app.application.auth.schemas import TokenResponse
from app.domain.exceptions import AuthenticationError
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
    auth_service.login.return_value = TokenResponse(access_token="jwt", expires_in=3600)

    response = client.post(
        "/auth/login",
        json={"email": "alice@kanea.ai", "password": "hunter2"},  # pragma: allowlist secret
    )

    assert response.status_code == 200
    assert response.json() == {
        "access_token": "jwt",
        "token_type": "bearer",
        "expires_in": 3600,
    }
    auth_service.login.assert_awaited_once()


def test_login_invalid_credentials_returns_401(client: TestClient, auth_service: AsyncMock) -> None:
    auth_service.login.side_effect = AuthenticationError("invalid email or password")

    response = client.post(
        "/auth/login",
        json={"email": "alice@kanea.ai", "password": "hunter2"},  # pragma: allowlist secret
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "invalid email or password"
    assert response.headers["www-authenticate"] == "Bearer"


def test_login_validation_error_returns_422(client: TestClient) -> None:
    response = client.post("/auth/login", json={"email": "not-an-email", "password": ""})
    assert response.status_code == 422


def test_agent_token_returns_token(client: TestClient, auth_service: AsyncMock) -> None:
    auth_service.issue_agent_token.return_value = TokenResponse(
        access_token="agent-jwt", expires_in=900
    )

    response = client.post("/auth/agent-token", json={"agent_id": str(uuid4()), "secret": "s3cret"})

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"] == "agent-jwt"
    assert body["expires_in"] == 900
    auth_service.issue_agent_token.assert_awaited_once()


def test_agent_token_invalid_returns_401(client: TestClient, auth_service: AsyncMock) -> None:
    auth_service.issue_agent_token.side_effect = AuthenticationError("invalid agent credentials")

    response = client.post("/auth/agent-token", json={"agent_id": str(uuid4()), "secret": "x"})

    assert response.status_code == 401
    assert response.json()["detail"] == "invalid agent credentials"


def test_agent_token_validation_error_returns_422(client: TestClient) -> None:
    response = client.post("/auth/agent-token", json={"agent_id": "not-a-uuid", "secret": "s"})
    assert response.status_code == 422
