"""Route + service tests for the BLOCKED workflow.

Covers:
* GET /tasks?status_filter=BLOCKED returns only blocked tasks
* PATCH /tasks/{id}/status enforces the transition table
* The headline path: BLOCKED -> IN_PROGRESS clears blocked_reason
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_principal, get_task_service
from app.application.tasks.schemas import (
    Principal,
    TaskResponse,
    UpdateTaskStatusRequest,
)
from app.application.tasks.service import TaskService
from app.domain.enums import MemberType, TaskStatus
from app.domain.exceptions import InvalidStatusTransitionError, TaskNotFoundError
from app.main import app
from tests.tasks.factories import make_principal, make_task


def _principal(*, priority: int = 1, workspace_id=None) -> Principal:
    return Principal(
        member_id=uuid4(),
        workspace_id=workspace_id or uuid4(),
        type=MemberType.HUMAN,
        priority=priority,
        scope="human",
    )


def _task_response(
    *,
    status: TaskStatus,
    blocked_reason: str | None = None,
    workspace_id=None,
) -> TaskResponse:
    now = datetime.now(UTC)
    return TaskResponse(
        id=uuid4(),
        workspace_id=workspace_id or uuid4(),
        created_by_id=uuid4(),
        title="Investigate latency spike",
        status=status,
        priority=3,
        description=None,
        assignee_id=None,
        due_at=None,
        blocked_reason=blocked_reason,
        created_at=now,
        updated_at=now,
    )


# ---------- route tests ----------


@pytest.fixture
def task_service() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def principal() -> Principal:
    return _principal()


@pytest.fixture
def client(task_service: AsyncMock, principal: Principal) -> Iterator[TestClient]:
    app.dependency_overrides[get_task_service] = lambda: task_service
    app.dependency_overrides[get_current_principal] = lambda: principal
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_list_tasks_filters_by_status(client: TestClient, task_service: AsyncMock) -> None:
    blocked = _task_response(status=TaskStatus.BLOCKED, blocked_reason="api 429s")
    task_service.list_for_workspace.return_value = [blocked]

    response = client.get(
        "/tasks?status_filter=BLOCKED",
        headers={"Authorization": "Bearer dummy"},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["status"] == "BLOCKED"
    assert body[0]["blocked_reason"] == "api 429s"
    task_service.list_for_workspace.assert_awaited_once()
    _, kwargs = task_service.list_for_workspace.call_args
    assert kwargs["status"] is TaskStatus.BLOCKED


def test_list_tasks_without_filter_returns_all(client: TestClient, task_service: AsyncMock) -> None:
    task_service.list_for_workspace.return_value = []

    response = client.get("/tasks", headers={"Authorization": "Bearer dummy"})

    assert response.status_code == 200
    _, kwargs = task_service.list_for_workspace.call_args
    assert kwargs["status"] is None


def test_resolve_blocked_task_returns_in_progress(
    client: TestClient, task_service: AsyncMock
) -> None:
    """Headline Resolve flow: BLOCKED -> IN_PROGRESS, blocked_reason cleared."""
    task_service.update_status.return_value = _task_response(
        status=TaskStatus.IN_PROGRESS, blocked_reason=None
    )

    response = client.patch(
        f"/tasks/{uuid4()}/status",
        json={"status": "IN_PROGRESS"},
        headers={"Authorization": "Bearer dummy"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "IN_PROGRESS"
    assert body["blocked_reason"] is None


def test_invalid_transition_returns_409(client: TestClient, task_service: AsyncMock) -> None:
    task_service.update_status.side_effect = InvalidStatusTransitionError(
        "cannot transition task from DONE to IN_PROGRESS"
    )

    response = client.patch(
        f"/tasks/{uuid4()}/status",
        json={"status": "IN_PROGRESS"},
        headers={"Authorization": "Bearer dummy"},
    )

    assert response.status_code == 409


def test_status_update_unknown_task_returns_404(
    client: TestClient, task_service: AsyncMock
) -> None:
    task_service.update_status.side_effect = TaskNotFoundError("task not found")

    response = client.patch(
        f"/tasks/{uuid4()}/status",
        json={"status": "IN_PROGRESS"},
        headers={"Authorization": "Bearer dummy"},
    )

    assert response.status_code == 404


def test_status_update_invalid_status_value_returns_422(client: TestClient) -> None:
    response = client.patch(
        f"/tasks/{uuid4()}/status",
        json={"status": "NOT_A_STATUS"},
        headers={"Authorization": "Bearer dummy"},
    )
    assert response.status_code == 422


# ---------- service-level transition table ----------


@pytest.fixture
def task_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def member_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(task_repo: AsyncMock, member_repo: AsyncMock) -> TaskService:
    return TaskService(tasks=task_repo, members=member_repo)


async def test_resolve_blocked_clears_blocked_reason(
    service: TaskService, task_repo: AsyncMock
) -> None:
    workspace_id = uuid4()
    requester = make_principal(workspace_id=workspace_id, priority=1)
    blocked = make_task(workspace_id=workspace_id, status=TaskStatus.BLOCKED)
    blocked.blocked_reason = "rate limited by upstream"
    task_repo.get_by_id.return_value = blocked
    task_repo.update_status.return_value = make_task(
        task_id=blocked.id, workspace_id=workspace_id, status=TaskStatus.IN_PROGRESS
    )

    await service.update_status(
        blocked.id,
        UpdateTaskStatusRequest(status=TaskStatus.IN_PROGRESS),
        requester,
    )

    task_repo.update_status.assert_awaited_once_with(
        task_id=blocked.id,
        status=TaskStatus.IN_PROGRESS,
        blocked_reason=None,
    )


async def test_blocking_a_task_persists_reason(service: TaskService, task_repo: AsyncMock) -> None:
    workspace_id = uuid4()
    requester = make_principal(workspace_id=workspace_id, priority=1)
    in_progress = make_task(workspace_id=workspace_id, status=TaskStatus.IN_PROGRESS)
    task_repo.get_by_id.return_value = in_progress
    task_repo.update_status.return_value = in_progress

    await service.update_status(
        in_progress.id,
        UpdateTaskStatusRequest(status=TaskStatus.BLOCKED, blocked_reason="missing creds"),
        requester,
    )

    task_repo.update_status.assert_awaited_once_with(
        task_id=in_progress.id,
        status=TaskStatus.BLOCKED,
        blocked_reason="missing creds",
    )


@pytest.mark.parametrize(
    ("from_status", "to_status"),
    [
        (TaskStatus.DONE, TaskStatus.IN_PROGRESS),
        (TaskStatus.CANCELLED, TaskStatus.IN_PROGRESS),
        (TaskStatus.PENDING, TaskStatus.DONE),
        (TaskStatus.PENDING, TaskStatus.BLOCKED),
        (TaskStatus.BLOCKED, TaskStatus.DONE),
    ],
)
async def test_invalid_transitions_are_rejected(
    service: TaskService,
    task_repo: AsyncMock,
    from_status: TaskStatus,
    to_status: TaskStatus,
) -> None:
    workspace_id = uuid4()
    requester = make_principal(workspace_id=workspace_id, priority=1)
    task = make_task(workspace_id=workspace_id, status=from_status)
    task_repo.get_by_id.return_value = task

    with pytest.raises(InvalidStatusTransitionError):
        await service.update_status(task.id, UpdateTaskStatusRequest(status=to_status), requester)

    task_repo.update_status.assert_not_awaited()


async def test_list_for_workspace_passes_status_filter(
    service: TaskService, task_repo: AsyncMock
) -> None:
    workspace_id = uuid4()
    requester = make_principal(workspace_id=workspace_id, priority=1)
    task_repo.list_by_workspace.return_value = [
        make_task(workspace_id=workspace_id, status=TaskStatus.BLOCKED)
    ]

    result = await service.list_for_workspace(requester, status=TaskStatus.BLOCKED)

    assert len(result) == 1
    assert result[0].status is TaskStatus.BLOCKED
    task_repo.list_by_workspace.assert_awaited_once_with(workspace_id, status=TaskStatus.BLOCKED)
