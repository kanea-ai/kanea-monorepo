"""Negative-authorization tests for admin-mutating endpoints.

This module is the structural fix for the test-category gap that let
issue #46 slip through: the wider test suite asserts "the allowed
actor succeeds" extensively; it almost never asserts "the forbidden
actor is rejected." That asymmetry is the root cause. New gated
paths should land a negative-authz test here so the gap doesn't
reopen.

This commit lands the agent-route admin-gate tests (#46). The
companion tenants rank-gate tests (#51) land in the immediately-
following commit, which extends this module to cover the four
member-mutation paths under their own admin-power rule.

Rule under audit here:

- **Admin-only route gate** (#46): PATCH and DELETE on
  /api/v1/agents/{id} must reject any non-admin caller at the
  framework layer (``WorkspaceAdminDep``). A non-admin should never
  reach the service.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import jwt
import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_agent_service
from app.application.agents.schemas import AgentResponse
from app.core.config import settings
from app.domain.enums import MemberRole, MemberType


def _bearer(
    *,
    role: MemberRole,
    priority: int = 2,
    workspace_id: UUID | None = None,
) -> dict[str, str]:
    """Forge a workspace-scoped HUMAN JWT for route-level tests."""
    now = datetime.now(UTC)
    payload = {
        "iss": settings.jwt_issuer,
        "sub": str(uuid4()),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=1)).timestamp()),
        "workspace_id": str(workspace_id or uuid4()),
        "type": MemberType.HUMAN.value,
        "priority": priority,
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
    from app.main import app

    app.dependency_overrides[get_agent_service] = lambda: agent_service
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _agent_response_stub(name: str = "renamed") -> AgentResponse:
    return AgentResponse(
        id=uuid4(),
        workspace_id=uuid4(),
        name=name,
        priority=5,
        model=None,
        created_at=datetime.now(UTC),
        last_seen_at=None,
        health_status="STALE",
    )


# ===========================================================================
# Section 1 — #46: PATCH/DELETE /agents/{id} require admin at the route
# ===========================================================================
#
# These four tests pin the framework-layer admin gate on the two agent
# routes. Before #46's fix, both routes used PrincipalDep and accepted
# any authenticated workspace member; the negative-side assertion (USER
# → 403) was simply absent. With WorkspaceAdminDep in place plus the
# service-layer role assertion that POST /agents already has, a USER
# never reaches the handler.


def test_patch_agent_rejects_workspace_user_role(
    client: TestClient,
    agent_service: AsyncMock,
) -> None:
    """The route's admin gate must reject USER role with 403 BEFORE
    the service is touched. Mirrors the existing POST /agents pattern
    (test_create_agent_requires_admin)."""
    response = client.patch(
        f"/api/v1/agents/{uuid4()}",
        json={"name": "x"},
        headers=_bearer(role=MemberRole.WORKSPACE_USER),
    )
    assert response.status_code == 403
    agent_service.update_agent.assert_not_called()


def test_patch_agent_allows_admin_role(
    client: TestClient,
    agent_service: AsyncMock,
) -> None:
    """Positive pair for the negative test above — ADMIN passes the
    gate and reaches the handler."""
    agent_service.update_agent.return_value = _agent_response_stub()
    response = client.patch(
        f"/api/v1/agents/{uuid4()}",
        json={"name": "renamed"},
        headers=_bearer(role=MemberRole.WORKSPACE_ADMIN),
    )
    assert response.status_code == 200
    assert response.json()["name"] == "renamed"


def test_delete_agent_rejects_workspace_user_role(
    client: TestClient,
    agent_service: AsyncMock,
) -> None:
    """The DELETE route's admin gate must reject USER role with 403
    BEFORE the service is touched."""
    response = client.delete(
        f"/api/v1/agents/{uuid4()}",
        headers=_bearer(role=MemberRole.WORKSPACE_USER),
    )
    assert response.status_code == 403
    agent_service.delete_agent.assert_not_called()


def test_delete_agent_allows_admin_role(
    client: TestClient,
    agent_service: AsyncMock,
) -> None:
    """Positive pair — ADMIN passes the gate and the route 204s."""
    agent_service.delete_agent.return_value = None
    response = client.delete(
        f"/api/v1/agents/{uuid4()}",
        headers=_bearer(role=MemberRole.WORKSPACE_ADMIN),
    )
    assert response.status_code == 204
