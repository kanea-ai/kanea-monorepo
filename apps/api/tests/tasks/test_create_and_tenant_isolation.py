"""Coverage for POST /tasks (create) and tenant-isolation on GET /tasks/{id}.

Tenant isolation contract: a task in workspace A must not be visible
or modifiable by a principal whose workspace_id is B — the service
returns TaskNotFoundError (which the route maps to 404, indistinguish-
able from a non-existent task)."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.application.tasks.schemas import CreateTaskRequest
from app.application.tasks.service import TaskService
from app.domain.enums import TaskStatus
from app.domain.exceptions import TaskNotFoundError
from tests.auth.factories import make_human
from tests.tasks.factories import make_principal, make_task


@pytest.fixture
def task_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def members() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(
    task_repo: AsyncMock,
    members: AsyncMock,
    workspace_repo: AsyncMock,
    seq_allocator: AsyncMock,
) -> TaskService:
    return TaskService(
        tasks=task_repo,
        members=members,
        workspaces=workspace_repo,
        seq_allocator=seq_allocator,
    )


# ---------- create ----------


async def test_create_task_uses_principal_workspace_and_creator(
    service: TaskService, task_repo: AsyncMock
) -> None:
    """workspace_id and created_by_id are derived from the principal —
    not from the request body — even if the client tries to spoof them
    (Pydantic's `extra="forbid"` rejects extra fields outright)."""
    p = make_principal()
    task_repo.create.side_effect = lambda t: t

    response = await service.create(
        CreateTaskRequest(title="Investigate flaky test", priority=2),
        p,
    )

    task_repo.create.assert_awaited_once()
    persisted = task_repo.create.await_args.args[0]
    assert persisted.workspace_id == p.workspace_id
    assert persisted.created_by_id == p.member_id
    assert persisted.title == "Investigate flaky test"
    assert persisted.priority == 2
    assert persisted.status is TaskStatus.PENDING
    assert persisted.assignee_id is None

    assert response.workspace_id == p.workspace_id
    assert response.created_by_id == p.member_id


async def test_create_task_with_assignee_in_workspace_is_allowed(
    service: TaskService, task_repo: AsyncMock, members: AsyncMock
) -> None:
    p = make_principal()
    assignee = make_human(workspace_id=p.workspace_id)
    members.get_by_id.return_value = assignee
    task_repo.create.side_effect = lambda t: t

    response = await service.create(
        CreateTaskRequest(title="Pair on the migration", assignee_id=assignee.id),
        p,
    )

    assert response.assignee_id == assignee.id
    members.get_by_id.assert_awaited_once_with(assignee.id)


async def test_create_task_assignee_outside_workspace_404s(
    service: TaskService, task_repo: AsyncMock, members: AsyncMock
) -> None:
    """A user can't task someone outside their workspace, even with a
    leaked member UUID — the service rejects."""
    p = make_principal()
    members.get_by_id.return_value = make_human(workspace_id=uuid4())  # other workspace

    with pytest.raises(TaskNotFoundError):
        await service.create(
            CreateTaskRequest(title="Cross-tenant attempt", assignee_id=uuid4()), p
        )

    task_repo.create.assert_not_called()


async def test_create_task_unknown_assignee_404s(service: TaskService, members: AsyncMock) -> None:
    p = make_principal()
    members.get_by_id.return_value = None
    with pytest.raises(TaskNotFoundError):
        await service.create(CreateTaskRequest(title="x", assignee_id=uuid4()), p)


# ---------- get_by_id (tenant isolation) ----------


async def test_get_by_id_returns_task_in_same_workspace(
    service: TaskService, task_repo: AsyncMock
) -> None:
    p = make_principal()
    task = make_task(workspace_id=p.workspace_id)
    task_repo.get_by_id.return_value = task

    response = await service.get_by_id(task.id, p)

    assert response.id == task.id


async def test_get_by_id_404s_for_task_in_other_workspace(
    service: TaskService, task_repo: AsyncMock
) -> None:
    """The task exists, but in a different workspace — must look like
    'not found' to the caller. Same-shape error as truly-missing tasks
    so a workspace-side enumeration attack can't distinguish."""
    p = make_principal()
    task_repo.get_by_id.return_value = make_task(workspace_id=uuid4())

    with pytest.raises(TaskNotFoundError):
        await service.get_by_id(uuid4(), p)


async def test_get_by_id_404s_when_missing(service: TaskService, task_repo: AsyncMock) -> None:
    p = make_principal()
    task_repo.get_by_id.return_value = None
    with pytest.raises(TaskNotFoundError):
        await service.get_by_id(uuid4(), p)
