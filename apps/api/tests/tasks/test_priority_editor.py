"""Phase 4 priority editor.

Allowed when the principal is a workspace OWNER/ADMIN OR the task's
team has the principal as HEAD/MANAGER. Plain MEMBERs (and LEADs,
who can re-delegate but don't move scheduling priority) get 403."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.application.tasks.schemas import UpdateTaskPriorityRequest
from app.application.tasks.service import TaskService
from app.domain.entities import Member
from app.domain.enums import MemberRole, MemberType, TaskStatus, TeamRole
from app.domain.exceptions import CrossTeamForbiddenError
from tests.tasks.factories import make_principal, make_task


def _member(
    *,
    member_id,
    workspace_id,
    team_id=None,
    team_role=None,
    role: MemberRole = MemberRole.WORKSPACE_USER,
) -> Member:
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    return Member(
        id=member_id,
        workspace_id=workspace_id,
        type=MemberType.HUMAN,
        name="Test",
        priority=5,
        team_id=team_id,
        team_role=team_role,
        role=role,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def task_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def member_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def activities() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(
    task_repo: AsyncMock,
    member_repo: AsyncMock,
    workspace_repo: AsyncMock,
    seq_allocator: AsyncMock,
    activities: AsyncMock,
) -> TaskService:
    return TaskService(
        tasks=task_repo,
        members=member_repo,
        workspaces=workspace_repo,
        seq_allocator=seq_allocator,
        activities=activities,
    )


async def test_owner_can_change_priority(
    service: TaskService, task_repo: AsyncMock, activities: AsyncMock
) -> None:
    ws = uuid4()
    requester = make_principal(workspace_id=ws, role=MemberRole.WORKSPACE_OWNER)
    task = make_task(workspace_id=ws, status=TaskStatus.PENDING, priority=5, team_id=None)
    task_repo.get_by_id.return_value = task
    task_repo.update_priority.return_value = make_task(task_id=task.id, workspace_id=ws, priority=2)

    result = await service.update_priority(
        task.id, UpdateTaskPriorityRequest(priority=2), requester
    )
    assert result.priority == 2
    task_repo.update_priority.assert_awaited_once_with(task.id, 2)
    activities.create.assert_awaited_once()


async def test_admin_can_change_priority(service: TaskService, task_repo: AsyncMock) -> None:
    ws = uuid4()
    requester = make_principal(workspace_id=ws, role=MemberRole.WORKSPACE_ADMIN)
    task = make_task(workspace_id=ws, priority=5)
    task_repo.get_by_id.return_value = task
    task_repo.update_priority.return_value = make_task(task_id=task.id, workspace_id=ws, priority=1)
    result = await service.update_priority(
        task.id, UpdateTaskPriorityRequest(priority=1), requester
    )
    assert result.priority == 1


async def test_team_manager_on_same_team_can_change(
    service: TaskService, task_repo: AsyncMock, member_repo: AsyncMock
) -> None:
    ws = uuid4()
    team = uuid4()
    requester = make_principal(workspace_id=ws, role=MemberRole.WORKSPACE_USER)
    task = make_task(workspace_id=ws, priority=5, team_id=team)
    task_repo.get_by_id.return_value = task
    member_repo.get_by_id.return_value = _member(
        member_id=requester.member_id,
        workspace_id=ws,
        team_id=team,
        team_role=TeamRole.MANAGER,
    )
    task_repo.update_priority.return_value = make_task(
        task_id=task.id, workspace_id=ws, priority=2, team_id=team
    )

    result = await service.update_priority(
        task.id, UpdateTaskPriorityRequest(priority=2), requester
    )
    assert result.priority == 2


async def test_team_lead_cannot_change_priority(
    service: TaskService, task_repo: AsyncMock, member_repo: AsyncMock
) -> None:
    ws = uuid4()
    team = uuid4()
    requester = make_principal(workspace_id=ws, role=MemberRole.WORKSPACE_USER)
    task_repo.get_by_id.return_value = make_task(workspace_id=ws, team_id=team)
    member_repo.get_by_id.return_value = _member(
        member_id=requester.member_id,
        workspace_id=ws,
        team_id=team,
        team_role=TeamRole.LEAD,
    )
    with pytest.raises(CrossTeamForbiddenError):
        await service.update_priority(uuid4(), UpdateTaskPriorityRequest(priority=2), requester)


async def test_manager_on_other_team_cannot_change(
    service: TaskService, task_repo: AsyncMock, member_repo: AsyncMock
) -> None:
    ws = uuid4()
    requester = make_principal(workspace_id=ws, role=MemberRole.WORKSPACE_USER)
    task_repo.get_by_id.return_value = make_task(workspace_id=ws, team_id=uuid4())
    member_repo.get_by_id.return_value = _member(
        member_id=requester.member_id,
        workspace_id=ws,
        team_id=uuid4(),
        team_role=TeamRole.MANAGER,
    )
    with pytest.raises(CrossTeamForbiddenError):
        await service.update_priority(uuid4(), UpdateTaskPriorityRequest(priority=2), requester)


async def test_plain_member_cannot_change_priority(
    service: TaskService, task_repo: AsyncMock, member_repo: AsyncMock
) -> None:
    ws = uuid4()
    requester = make_principal(workspace_id=ws, role=MemberRole.WORKSPACE_USER)
    task_repo.get_by_id.return_value = make_task(workspace_id=ws, team_id=uuid4())
    member_repo.get_by_id.return_value = _member(member_id=requester.member_id, workspace_id=ws)
    with pytest.raises(CrossTeamForbiddenError):
        await service.update_priority(uuid4(), UpdateTaskPriorityRequest(priority=2), requester)


async def test_no_op_when_priority_unchanged(service: TaskService, task_repo: AsyncMock) -> None:
    """Submitting the current priority is a no-op — we skip the RBAC
    check, the DB write, and the activity event so a stray re-save
    from a refresh doesn't create audit noise."""
    ws = uuid4()
    requester = make_principal(workspace_id=ws, role=MemberRole.WORKSPACE_USER)
    task = make_task(workspace_id=ws, priority=4)
    task_repo.get_by_id.return_value = task

    result = await service.update_priority(
        task.id, UpdateTaskPriorityRequest(priority=4), requester
    )
    assert result.priority == 4
    task_repo.update_priority.assert_not_called()
