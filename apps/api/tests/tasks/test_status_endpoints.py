"""Route + service tests for task status transitions and the
orthogonal blocked-flag.

Contract (after batch 2):

- TaskStatus is restricted to PENDING / IN_PROGRESS / DONE / CANCELLED.
- Being "blocked" is a separate boolean flag (`is_blocked`), toggled
  via PATCH /tasks/{id}/block — never via the status endpoint.
- The Exception Queue queries `?blocked_only=true`.
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
    SetBlockedRequest,
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
    is_blocked: bool = False,
    blocked_reason: str | None = None,
    workspace_id=None,
    seq: int = 1,
    public_id: str = "TASK-001",
) -> TaskResponse:
    now = datetime.now(UTC)
    return TaskResponse(
        id=uuid4(),
        workspace_id=workspace_id or uuid4(),
        created_by_id=uuid4(),
        title="Investigate latency spike",
        status=status,
        priority=3,
        seq=seq,
        public_id=public_id,
        description=None,
        assignee_id=None,
        project_id=None,
        team_id=None,
        due_at=None,
        is_blocked=is_blocked,
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


def test_list_tasks_with_blocked_filter(client: TestClient, task_service: AsyncMock) -> None:
    blocked = _task_response(
        status=TaskStatus.IN_PROGRESS,
        is_blocked=True,
        blocked_reason="api 429s",
    )
    task_service.list_for_workspace.return_value = [blocked]

    response = client.get(
        "/api/v1/tasks?blocked_only=true",
        headers={"Authorization": "Bearer dummy"},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["status"] == "IN_PROGRESS"
    assert body[0]["is_blocked"] is True
    assert body[0]["blocked_reason"] == "api 429s"
    assert body[0]["public_id"] == "TASK-001"
    _, kwargs = task_service.list_for_workspace.call_args
    assert kwargs["blocked_only"] is True
    assert kwargs["status"] is None


def test_list_tasks_with_status_filter(client: TestClient, task_service: AsyncMock) -> None:
    task_service.list_for_workspace.return_value = []

    response = client.get(
        "/api/v1/tasks?status_filter=IN_PROGRESS",
        headers={"Authorization": "Bearer dummy"},
    )

    assert response.status_code == 200
    _, kwargs = task_service.list_for_workspace.call_args
    assert kwargs["status"] is TaskStatus.IN_PROGRESS
    assert kwargs["blocked_only"] is False


def test_list_tasks_without_filter_returns_all(client: TestClient, task_service: AsyncMock) -> None:
    task_service.list_for_workspace.return_value = []

    response = client.get("/api/v1/tasks", headers={"Authorization": "Bearer dummy"})

    assert response.status_code == 200
    _, kwargs = task_service.list_for_workspace.call_args
    assert kwargs["status"] is None
    assert kwargs["blocked_only"] is False


def test_status_filter_rejects_blocked_value(client: TestClient) -> None:
    """BLOCKED is no longer a status. The TaskStatus enum doesn't include
    it, so passing it via ?status_filter must surface a 422."""
    response = client.get(
        "/api/v1/tasks?status_filter=BLOCKED",
        headers={"Authorization": "Bearer dummy"},
    )
    assert response.status_code == 422


def test_status_update_rejects_blocked_value(client: TestClient) -> None:
    """PATCH /tasks/{id}/status no longer accepts BLOCKED — clients must
    use PATCH /tasks/{id}/block instead."""
    response = client.patch(
        f"/api/v1/tasks/{uuid4()}/status",
        json={"status": "BLOCKED"},
        headers={"Authorization": "Bearer dummy"},
    )
    assert response.status_code == 422


def test_block_endpoint_sets_flag_and_reason(client: TestClient, task_service: AsyncMock) -> None:
    task_service.set_blocked.return_value = _task_response(
        status=TaskStatus.IN_PROGRESS,
        is_blocked=True,
        blocked_reason="missing creds",
    )

    response = client.patch(
        f"/api/v1/tasks/{uuid4()}/block",
        json={"is_blocked": True, "reason": "missing creds"},
        headers={"Authorization": "Bearer dummy"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["is_blocked"] is True
    assert body["blocked_reason"] == "missing creds"
    task_service.set_blocked.assert_awaited_once()


def test_unblock_clears_reason(client: TestClient, task_service: AsyncMock) -> None:
    task_service.set_blocked.return_value = _task_response(
        status=TaskStatus.IN_PROGRESS,
        is_blocked=False,
        blocked_reason=None,
    )

    response = client.patch(
        f"/api/v1/tasks/{uuid4()}/block",
        json={"is_blocked": False},
        headers={"Authorization": "Bearer dummy"},
    )

    assert response.status_code == 200
    assert response.json()["blocked_reason"] is None


def test_block_endpoint_unknown_task_returns_404(
    client: TestClient, task_service: AsyncMock
) -> None:
    task_service.set_blocked.side_effect = TaskNotFoundError("task not found")
    response = client.patch(
        f"/api/v1/tasks/{uuid4()}/block",
        json={"is_blocked": True, "reason": "x"},
        headers={"Authorization": "Bearer dummy"},
    )
    assert response.status_code == 404


def test_status_change_to_done(client: TestClient, task_service: AsyncMock) -> None:
    task_service.update_status.return_value = _task_response(status=TaskStatus.DONE)

    response = client.patch(
        f"/api/v1/tasks/{uuid4()}/status",
        json={"status": "DONE"},
        headers={"Authorization": "Bearer dummy"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "DONE"


def test_invalid_transition_returns_409(client: TestClient, task_service: AsyncMock) -> None:
    task_service.update_status.side_effect = InvalidStatusTransitionError(
        "cannot transition task from DONE to IN_PROGRESS"
    )
    response = client.patch(
        f"/api/v1/tasks/{uuid4()}/status",
        json={"status": "IN_PROGRESS"},
        headers={"Authorization": "Bearer dummy"},
    )
    assert response.status_code == 409


def test_status_update_unknown_task_returns_404(
    client: TestClient, task_service: AsyncMock
) -> None:
    task_service.update_status.side_effect = TaskNotFoundError("task not found")
    response = client.patch(
        f"/api/v1/tasks/{uuid4()}/status",
        json={"status": "IN_PROGRESS"},
        headers={"Authorization": "Bearer dummy"},
    )
    assert response.status_code == 404


def test_status_update_invalid_status_value_returns_422(client: TestClient) -> None:
    response = client.patch(
        f"/api/v1/tasks/{uuid4()}/status",
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
def workspace_repo() -> AsyncMock:
    repo = AsyncMock()
    # Default prefix used by from_entity calls — service tests don't
    # generally inspect the prefix; the public_id assertion lives in
    # dedicated tests.
    from app.domain.entities import Workspace

    repo.get_by_id.return_value = Workspace(
        id=uuid4(),
        name="Test",
        slug="test",
        task_prefix="TASK",
        next_task_seq=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    return repo


@pytest.fixture
def seq_allocator() -> AsyncMock:
    repo = AsyncMock()
    repo.allocate_next_task_seq.return_value = (1, "TASK")
    return repo


@pytest.fixture
def service(
    task_repo: AsyncMock,
    member_repo: AsyncMock,
    workspace_repo: AsyncMock,
    seq_allocator: AsyncMock,
) -> TaskService:
    return TaskService(
        tasks=task_repo,
        members=member_repo,
        workspaces=workspace_repo,
        seq_allocator=seq_allocator,
    )


async def test_set_blocked_persists_reason(service: TaskService, task_repo: AsyncMock) -> None:
    workspace_id = uuid4()
    requester = make_principal(workspace_id=workspace_id, priority=1)
    task = make_task(workspace_id=workspace_id, status=TaskStatus.IN_PROGRESS)
    task_repo.get_by_id.return_value = task
    task_repo.set_blocked.return_value = make_task(
        task_id=task.id,
        workspace_id=workspace_id,
        status=TaskStatus.IN_PROGRESS,
        is_blocked=True,
        blocked_reason="missing creds",
    )

    await service.set_blocked(
        task.id,
        SetBlockedRequest(is_blocked=True, reason="missing creds"),
        requester,
    )

    task_repo.set_blocked.assert_awaited_once_with(
        task_id=task.id,
        is_blocked=True,
        blocked_reason="missing creds",
    )


async def test_service_unblock_clears_reason(service: TaskService, task_repo: AsyncMock) -> None:
    workspace_id = uuid4()
    requester = make_principal(workspace_id=workspace_id, priority=1)
    task = make_task(
        workspace_id=workspace_id,
        status=TaskStatus.IN_PROGRESS,
        is_blocked=True,
        blocked_reason="upstream 429",
    )
    task_repo.get_by_id.return_value = task
    task_repo.set_blocked.return_value = make_task(
        task_id=task.id,
        workspace_id=workspace_id,
        status=TaskStatus.IN_PROGRESS,
    )

    # Even if a reason is supplied while unblocking, the service drops it.
    await service.set_blocked(
        task.id,
        SetBlockedRequest(is_blocked=False, reason="ignored"),
        requester,
    )

    task_repo.set_blocked.assert_awaited_once_with(
        task_id=task.id,
        is_blocked=False,
        blocked_reason=None,
    )


async def test_status_update_does_not_touch_blocked_reason(
    service: TaskService, task_repo: AsyncMock
) -> None:
    """Status updates and blocked-flag are orthogonal — completing a
    task while it's blocked is a real possibility (e.g. cancelled
    while waiting on creds) and the blocked_reason should survive."""
    workspace_id = uuid4()
    requester = make_principal(workspace_id=workspace_id, priority=1)
    task = make_task(
        workspace_id=workspace_id,
        status=TaskStatus.IN_PROGRESS,
        is_blocked=True,
        blocked_reason="upstream 429",
    )
    task_repo.get_by_id.return_value = task
    task_repo.update_status.return_value = task

    await service.update_status(
        task.id,
        UpdateTaskStatusRequest(status=TaskStatus.CANCELLED),
        requester,
    )

    # The repo update_status call no longer takes blocked_reason.
    task_repo.update_status.assert_awaited_once_with(
        task_id=task.id,
        status=TaskStatus.CANCELLED,
        tokens_used=None,
    )


@pytest.mark.parametrize(
    ("from_status", "to_status"),
    [
        # IN_PROGRESS -> IN_REVIEW: executor flags the work for verification.
        (TaskStatus.IN_PROGRESS, TaskStatus.IN_REVIEW),
        # IN_REVIEW -> DONE: reviewer approves.
        (TaskStatus.IN_REVIEW, TaskStatus.DONE),
        # IN_REVIEW -> IN_PROGRESS: reviewer rejects, kicks back.
        (TaskStatus.IN_REVIEW, TaskStatus.IN_PROGRESS),
        # IN_REVIEW -> CANCELLED: scope drops mid-review.
        (TaskStatus.IN_REVIEW, TaskStatus.CANCELLED),
    ],
)
async def test_in_review_transitions_are_allowed(
    service: TaskService,
    task_repo: AsyncMock,
    from_status: TaskStatus,
    to_status: TaskStatus,
) -> None:
    workspace_id = uuid4()
    requester = make_principal(workspace_id=workspace_id, priority=1)
    task = make_task(workspace_id=workspace_id, status=from_status)
    task_repo.get_by_id.return_value = task
    task_repo.update_status.return_value = make_task(
        task_id=task.id, workspace_id=workspace_id, status=to_status
    )

    await service.update_status(task.id, UpdateTaskStatusRequest(status=to_status), requester)

    task_repo.update_status.assert_awaited_once()


@pytest.mark.parametrize(
    ("from_status", "to_status"),
    [
        (TaskStatus.DONE, TaskStatus.IN_PROGRESS),
        (TaskStatus.CANCELLED, TaskStatus.IN_PROGRESS),
        (TaskStatus.PENDING, TaskStatus.DONE),
        (TaskStatus.DONE, TaskStatus.CANCELLED),
        (TaskStatus.CANCELLED, TaskStatus.DONE),
        # PENDING can't skip straight to IN_REVIEW — must go through
        # IN_PROGRESS first so the activity log captures the work.
        (TaskStatus.PENDING, TaskStatus.IN_REVIEW),
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


async def test_list_for_workspace_passes_blocked_only(
    service: TaskService, task_repo: AsyncMock
) -> None:
    workspace_id = uuid4()
    requester = make_principal(workspace_id=workspace_id, priority=1)
    task_repo.list_by_workspace.return_value = [
        make_task(workspace_id=workspace_id, status=TaskStatus.IN_PROGRESS, is_blocked=True)
    ]

    result = await service.list_for_workspace(requester, blocked_only=True)

    assert len(result) == 1
    assert result[0].is_blocked is True
    task_repo.list_by_workspace.assert_awaited_once_with(
        workspace_id,
        status=None,
        blocked_only=True,
        project_id=None,
        team_id=None,
        assignee_id=None,
    )


async def test_list_for_workspace_passes_status_filter(
    service: TaskService, task_repo: AsyncMock
) -> None:
    workspace_id = uuid4()
    requester = make_principal(workspace_id=workspace_id, priority=1)
    task_repo.list_by_workspace.return_value = [
        make_task(workspace_id=workspace_id, status=TaskStatus.IN_PROGRESS)
    ]

    result = await service.list_for_workspace(requester, status=TaskStatus.IN_PROGRESS)

    assert len(result) == 1
    assert result[0].status is TaskStatus.IN_PROGRESS
    task_repo.list_by_workspace.assert_awaited_once_with(
        workspace_id,
        status=TaskStatus.IN_PROGRESS,
        blocked_only=False,
        project_id=None,
        team_id=None,
        assignee_id=None,
    )
