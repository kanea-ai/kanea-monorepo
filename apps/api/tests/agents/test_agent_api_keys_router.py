"""Router-layer wiring for the agent API-key endpoints.

Covers:
- POST /api/v1/agents — now WorkspaceAdminDep (was PrincipalDep)
- POST /api/v1/agents/{id}/api-keys
- GET  /api/v1/agents/{id}/api-keys
- DELETE /api/v1/agents/{id}/api-keys/{key_id}

Service-layer behaviour is exercised by
``test_agent_api_keys_service.py``; this file just confirms that the
route maps request → service call → response, and that admin gating
trips at the framework layer (403 with a USER role, 401 with no token).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_agent_service
from app.application.agents.schemas import (
    AgentApiKeyResponse,
    AgentDetailResponse,
    AgentResponse,
    AgentStatsResponse,
    CreateAgentResponse,
    IssueAgentApiKeyResponse,
)
from app.core.config import settings
from app.domain.enums import MemberRole, MemberType
from app.domain.exceptions import (
    AgentApiKeyNotFoundError,
    AgentHasCreatedTasksError,
    AgentNotFoundError,
    ForbiddenError,
)
from app.main import app


def _bearer(*, role: MemberRole = MemberRole.WORKSPACE_OWNER) -> dict[str, str]:
    """Forge a workspace-scoped human JWT with the given role."""
    now = datetime.now(UTC)
    payload = {
        "iss": settings.jwt_issuer,
        "sub": str(uuid4()),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=1)).timestamp()),
        "workspace_id": str(uuid4()),
        "type": MemberType.HUMAN.value,
        "priority": 1 if role is MemberRole.WORKSPACE_OWNER else 2,
        "role": role.value,
        "scope": "human",
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def agent_service() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def client(agent_service: AsyncMock) -> Iterator[TestClient]:
    app.dependency_overrides[get_agent_service] = lambda: agent_service
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


# ---------- POST /api/v1/agents (tightened to admin) ----------


def test_create_agent_requires_admin(client: TestClient) -> None:
    """USER role gets the WorkspaceAdminDep 403 before the handler runs.
    No service-side mocking needed — the dep rejects upstream."""
    response = client.post(
        "/api/v1/agents",
        json={"name": "bot"},
        headers=_bearer(role=MemberRole.WORKSPACE_USER),
    )
    assert response.status_code == 403


def test_create_agent_admin_path_routes_through_service(
    client: TestClient, agent_service: AsyncMock
) -> None:
    agent_id = uuid4()
    workspace_id = uuid4()
    agent_service.create_agent.return_value = CreateAgentResponse(
        id=agent_id,
        workspace_id=workspace_id,
        name="bot",
        priority=5,
        model=None,
        api_key="kna_dev_AbCdEf...",  # pragma: allowlist secret
    )
    response = client.post("/api/v1/agents", json={"name": "bot"}, headers=_bearer())
    assert response.status_code == 201
    assert response.json()["api_key"].startswith("kna_dev_")


def test_create_agent_propagates_service_forbidden(
    client: TestClient, agent_service: AsyncMock
) -> None:
    """The service-layer ForbiddenError is the belt-and-braces against
    the route's WorkspaceAdminDep. A non-admin token never reaches the
    handler, but a misconfigured dep + the service re-assertion still
    surface as 403 via the explicit except branch."""
    agent_service.create_agent.side_effect = ForbiddenError("nope")
    response = client.post("/api/v1/agents", json={"name": "bot"}, headers=_bearer())
    assert response.status_code == 403


# ---------- pre-existing endpoints — confirming behaviour survived the tighten ----------


def test_list_agents_returns_service_payload(client: TestClient, agent_service: AsyncMock) -> None:
    agent_service.list_agents.return_value = []
    response = client.get("/api/v1/agents", headers=_bearer())
    assert response.status_code == 200
    assert response.json() == []


def test_get_agent_detail_happy(client: TestClient, agent_service: AsyncMock) -> None:
    agent_id = uuid4()
    agent_service.get_agent_detail.return_value = AgentDetailResponse(
        id=agent_id,
        workspace_id=uuid4(),
        name="bot",
        priority=5,
        model=None,
        created_at=datetime.now(UTC),
        last_seen_at=None,
        health_status="STALE",
        stats=AgentStatsResponse(
            assigned_count=0,
            completed_count=0,
            avg_resolution_seconds=None,
            accuracy_percent=None,
            last_activity_at=None,
            total_tokens_used=0,
        ),
    )
    response = client.get(f"/api/v1/agents/{agent_id}", headers=_bearer())
    assert response.status_code == 200
    assert response.json()["health_status"] == "STALE"


def test_get_agent_detail_404(client: TestClient, agent_service: AsyncMock) -> None:
    agent_service.get_agent_detail.side_effect = AgentNotFoundError("agent not found")
    response = client.get(f"/api/v1/agents/{uuid4()}", headers=_bearer())
    assert response.status_code == 404


def test_update_agent_happy(client: TestClient, agent_service: AsyncMock) -> None:
    agent_service.update_agent.return_value = AgentResponse(
        id=uuid4(),
        workspace_id=uuid4(),
        name="renamed",
        priority=5,
        model=None,
        created_at=datetime.now(UTC),
        last_seen_at=None,
        health_status="STALE",
    )
    response = client.patch(
        f"/api/v1/agents/{uuid4()}",
        json={"name": "renamed"},
        headers=_bearer(),
    )
    assert response.status_code == 200
    assert response.json()["name"] == "renamed"


def test_update_agent_404(client: TestClient, agent_service: AsyncMock) -> None:
    agent_service.update_agent.side_effect = AgentNotFoundError("nope")
    response = client.patch(f"/api/v1/agents/{uuid4()}", json={}, headers=_bearer())
    assert response.status_code == 404


def test_delete_agent_happy(client: TestClient, agent_service: AsyncMock) -> None:
    agent_service.delete_agent.return_value = None
    response = client.delete(f"/api/v1/agents/{uuid4()}", headers=_bearer())
    assert response.status_code == 204


def test_delete_agent_404(client: TestClient, agent_service: AsyncMock) -> None:
    agent_service.delete_agent.side_effect = AgentNotFoundError("nope")
    response = client.delete(f"/api/v1/agents/{uuid4()}", headers=_bearer())
    assert response.status_code == 404


def test_delete_agent_409_when_has_created_tasks(
    client: TestClient, agent_service: AsyncMock
) -> None:
    agent_service.delete_agent.side_effect = AgentHasCreatedTasksError("nope")
    response = client.delete(f"/api/v1/agents/{uuid4()}", headers=_bearer())
    assert response.status_code == 409


# ---------- POST /api/v1/agents/{id}/api-keys ----------


def test_issue_api_key_requires_admin(client: TestClient) -> None:
    response = client.post(
        f"/api/v1/agents/{uuid4()}/api-keys",
        json={"label": "x"},
        headers=_bearer(role=MemberRole.WORKSPACE_USER),
    )
    assert response.status_code == 403


def test_issue_api_key_returns_plaintext(client: TestClient, agent_service: AsyncMock) -> None:
    agent_service.issue_api_key.return_value = IssueAgentApiKeyResponse(
        id=uuid4(),
        prefix="kna_dev_",
        last4="aBcD",
        label="ci-runner",
        created_at=datetime.now(UTC),
        api_key="kna_dev_AbCdEf...",  # pragma: allowlist secret
    )
    response = client.post(
        f"/api/v1/agents/{uuid4()}/api-keys",
        json={"label": "ci-runner"},
        headers=_bearer(),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["api_key"].startswith("kna_dev_")
    assert body["label"] == "ci-runner"


def test_issue_api_key_404_on_cross_workspace(client: TestClient, agent_service: AsyncMock) -> None:
    agent_service.issue_api_key.side_effect = AgentNotFoundError("agent not found")
    response = client.post(f"/api/v1/agents/{uuid4()}/api-keys", json={}, headers=_bearer())
    assert response.status_code == 404


def test_issue_api_key_403_on_service_forbidden(
    client: TestClient, agent_service: AsyncMock
) -> None:
    """The service-layer ForbiddenError mirrors the route-layer gate
    for defence-in-depth; the route propagates as 403."""
    agent_service.issue_api_key.side_effect = ForbiddenError("nope")
    response = client.post(f"/api/v1/agents/{uuid4()}/api-keys", json={}, headers=_bearer())
    assert response.status_code == 403


# ---------- GET /api/v1/agents/{id}/api-keys ----------


def test_list_api_keys_requires_admin(client: TestClient) -> None:
    response = client.get(
        f"/api/v1/agents/{uuid4()}/api-keys",
        headers=_bearer(role=MemberRole.WORKSPACE_USER),
    )
    assert response.status_code == 403


def test_list_api_keys_404_on_unknown_agent(client: TestClient, agent_service: AsyncMock) -> None:
    agent_service.list_api_keys.side_effect = AgentNotFoundError("nope")
    response = client.get(f"/api/v1/agents/{uuid4()}/api-keys", headers=_bearer())
    assert response.status_code == 404


def test_list_api_keys_403_on_service_forbidden(
    client: TestClient, agent_service: AsyncMock
) -> None:
    agent_service.list_api_keys.side_effect = ForbiddenError("nope")
    response = client.get(f"/api/v1/agents/{uuid4()}/api-keys", headers=_bearer())
    assert response.status_code == 403


def test_list_api_keys_returns_metadata_only(client: TestClient, agent_service: AsyncMock) -> None:
    agent_service.list_api_keys.return_value = [
        AgentApiKeyResponse(
            id=uuid4(),
            prefix="kna_dev_",
            last4="aBcD",
            label="primary",
            created_at=datetime.now(UTC),
            last_used_at=None,
            revoked_at=None,
        ),
    ]
    response = client.get(f"/api/v1/agents/{uuid4()}/api-keys", headers=_bearer())
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert "api_key" not in body[0]
    assert "secret_hash" not in body[0]


# ---------- DELETE /api/v1/agents/{id}/api-keys/{key_id} ----------


def test_revoke_api_key_requires_admin(client: TestClient) -> None:
    response = client.delete(
        f"/api/v1/agents/{uuid4()}/api-keys/{uuid4()}",
        headers=_bearer(role=MemberRole.WORKSPACE_USER),
    )
    assert response.status_code == 403


def test_revoke_api_key_204_on_success(client: TestClient, agent_service: AsyncMock) -> None:
    agent_service.revoke_api_key.return_value = None
    response = client.delete(f"/api/v1/agents/{uuid4()}/api-keys/{uuid4()}", headers=_bearer())
    assert response.status_code == 204


def test_revoke_api_key_404_when_key_unknown(client: TestClient, agent_service: AsyncMock) -> None:
    agent_service.revoke_api_key.side_effect = AgentApiKeyNotFoundError("not found")
    response = client.delete(f"/api/v1/agents/{uuid4()}/api-keys/{uuid4()}", headers=_bearer())
    assert response.status_code == 404


def test_revoke_api_key_404_when_agent_unknown(
    client: TestClient, agent_service: AsyncMock
) -> None:
    agent_service.revoke_api_key.side_effect = AgentNotFoundError("agent not found")
    response = client.delete(f"/api/v1/agents/{uuid4()}/api-keys/{uuid4()}", headers=_bearer())
    assert response.status_code == 404


def test_revoke_api_key_403_on_service_forbidden(
    client: TestClient, agent_service: AsyncMock
) -> None:
    agent_service.revoke_api_key.side_effect = ForbiddenError("nope")
    response = client.delete(f"/api/v1/agents/{uuid4()}/api-keys/{uuid4()}", headers=_bearer())
    assert response.status_code == 403
