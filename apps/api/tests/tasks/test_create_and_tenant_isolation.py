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
    # ``assignee_name`` is denormalised onto the response so the UI can
    # render a clickable name without a follow-up /tenants/members
    # lookup (which 403s for non-admins on cross-team members). The
    # create flow reuses the already-validated assignee, so we expect
    # exactly one members.get_by_id() round-trip.
    assert response.assignee_name == assignee.name
    members.get_by_id.assert_awaited_once_with(assignee.id)


async def test_create_task_without_assignee_returns_null_assignee_name(
    service: TaskService, task_repo: AsyncMock, members: AsyncMock
) -> None:
    """Unassigned create: ``assignee_name`` is None and the members repo
    is never consulted. Pins the frontend's 'Unassigned' label path."""
    p = make_principal()
    task_repo.create.side_effect = lambda t: t

    response = await service.create(CreateTaskRequest(title="No-one assigned yet"), p)

    assert response.assignee_id is None
    assert response.assignee_name is None
    members.get_by_id.assert_not_called()


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


# ---------- assignee_name resolution on the detail endpoint ----------


async def test_get_by_id_resolves_assignee_name_when_member_exists(
    service: TaskService, task_repo: AsyncMock, members: AsyncMock
) -> None:
    """Detail flow pins the resolved-name path: an assigned task's
    response carries the member's display name. Drives the linked
    indigo label on the Task UI."""
    p = make_principal()
    assignee = make_human(workspace_id=p.workspace_id)
    task = make_task(workspace_id=p.workspace_id, assignee_id=assignee.id)
    task_repo.get_by_id.return_value = task
    members.get_by_id.return_value = assignee

    response = await service.get_by_id(task.id, p)

    assert response.assignee_id == assignee.id
    assert response.assignee_name == assignee.name


async def test_get_by_id_assignee_name_is_null_for_unassigned_task(
    service: TaskService, task_repo: AsyncMock, members: AsyncMock
) -> None:
    """Unassigned task → ``assignee_name`` is null and the members repo
    is never consulted. Drives the 'Unassigned' italic label."""
    p = make_principal()
    task = make_task(workspace_id=p.workspace_id, assignee_id=None)
    task_repo.get_by_id.return_value = task

    response = await service.get_by_id(task.id, p)

    assert response.assignee_id is None
    assert response.assignee_name is None
    members.get_by_id.assert_not_called()


async def test_get_by_id_assignee_name_null_when_member_missing(
    service: TaskService, task_repo: AsyncMock, members: AsyncMock
) -> None:
    """Defensive fallback: ``assignee_id`` is set but the member can't
    be resolved (legacy data — under normal flow the ON DELETE SET
    NULL cascade on tasks.assignee_id would have nulled the FK). The
    response carries assignee_id but assignee_name is null, which the
    UI renders as the italic 'Former member' link."""
    p = make_principal()
    orphan_assignee_id = uuid4()
    task = make_task(workspace_id=p.workspace_id, assignee_id=orphan_assignee_id)
    task_repo.get_by_id.return_value = task
    members.get_by_id.return_value = None

    response = await service.get_by_id(task.id, p)

    assert response.assignee_id == orphan_assignee_id
    assert response.assignee_name is None
    members.get_by_id.assert_awaited_once_with(orphan_assignee_id)
