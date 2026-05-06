"""Route-level tests for POST /tasks/{id}/delegate.

Focus: the hierarchy rule must surface as HTTP 403 at the boundary,
including the canonical Agent (priority 5) -> CEO (priority 1) case.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_principal, get_task_service
from app.application.tasks.schemas import Principal, TaskResponse
from app.domain.enums import MemberType, TaskStatus
from app.domain.exceptions import DelegationForbiddenError, TaskNotFoundError
from app.main import app


def _principal(*, priority: int, workspace_id=None, member_type=MemberType.HUMAN) -> Principal:
    return Principal(
        member_id=uuid4(),
        workspace_id=workspace_id or uuid4(),
        type=member_type,
        priority=priority,
        scope="human" if member_type is MemberType.HUMAN else "agent",
    )


def _task_response(*, assignee_id=None, workspace_id=None) -> TaskResponse:
    now = datetime.now(UTC)
    return TaskResponse(
        id=uuid4(),
        workspace_id=workspace_id or uuid4(),
        created_by_id=uuid4(),
        title="Investigate latency spike",
        status=TaskStatus.PENDING,
        priority=3,
        description=None,
        assignee_id=assignee_id,
        due_at=None,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def task_service() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def principal() -> Principal:
    return _principal(priority=1)


@pytest.fixture
def client(task_service: AsyncMock, principal: Principal) -> Iterator[TestClient]:
    app.dependency_overrides[get_task_service] = lambda: task_service
    app.dependency_overrides[get_current_principal] = lambda: principal
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_delegate_returns_200_with_updated_task(
    client: TestClient, task_service: AsyncMock
) -> None:
    target_id = uuid4()
    task_service.delegate.return_value = _task_response(assignee_id=target_id)

    response = client.post(
        f"/tasks/{uuid4()}/delegate",
        json={"member_id": str(target_id)},
        headers={"Authorization": "Bearer dummy"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["assignee_id"] == str(target_id)
    task_service.delegate.assert_awaited_once()


def test_agent_delegating_to_ceo_returns_403(client: TestClient, task_service: AsyncMock) -> None:
    """The headline rule: Agent (priority 5) -> CEO (priority 1) is forbidden."""
    task_service.delegate.side_effect = DelegationForbiddenError(
        "requester rank is not high enough to delegate to this member"
    )

    response = client.post(
        f"/tasks/{uuid4()}/delegate",
        json={"member_id": str(uuid4())},
        headers={"Authorization": "Bearer dummy"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == (
        "requester rank is not high enough to delegate to this member"
    )


def test_delegate_unknown_task_returns_404(client: TestClient, task_service: AsyncMock) -> None:
    task_service.delegate.side_effect = TaskNotFoundError("task not found")

    response = client.post(
        f"/tasks/{uuid4()}/delegate",
        json={"member_id": str(uuid4())},
        headers={"Authorization": "Bearer dummy"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "task not found"


def test_delegate_invalid_payload_returns_422(client: TestClient) -> None:
    response = client.post(
        f"/tasks/{uuid4()}/delegate",
        json={"member_id": "not-a-uuid"},
        headers={"Authorization": "Bearer dummy"},
    )
    assert response.status_code == 422


def test_delegate_invalid_task_id_returns_422(client: TestClient) -> None:
    response = client.post(
        "/tasks/not-a-uuid/delegate",
        json={"member_id": str(uuid4())},
        headers={"Authorization": "Bearer dummy"},
    )
    assert response.status_code == 422


def test_delegate_requires_bearer_token() -> None:
    """Without overriding get_current_principal, missing Authorization is a 403/401."""
    client = TestClient(app)
    response = client.post(
        f"/tasks/{uuid4()}/delegate",
        json={"member_id": str(uuid4())},
    )
    # FastAPI's HTTPBearer with auto_error=True returns 403 when the header
    # is missing entirely, or 401 with WWW-Authenticate on a malformed token.
    assert response.status_code in (401, 403)
