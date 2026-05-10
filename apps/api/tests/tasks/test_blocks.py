"""Tests for the paginated Blocks list (TaskService.list_blocks).

The Blocks page is the only paginated task surface — the kanban
keeps its full unpaginated read. Service-level concerns covered
here:

- Filters + sort forward to the repo verbatim.
- Default sort is ``PRIORITY`` (high-rank-first).
- Non-admin principals get their ``assignee_id`` filter silently
  overridden with their own member id, even if they pass another.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.application.tasks.service import TaskService
from app.domain.entities import Task
from app.domain.enums import BlocksSort, MemberRole, TaskStatus
from tests.tasks.factories import make_principal


def _task(workspace_id, *, title: str, priority: int = 5, assignee_id=None) -> Task:
    now = datetime.now(UTC)
    return Task(
        id=uuid4(),
        workspace_id=workspace_id,
        created_by_id=uuid4(),
        title=title,
        status=TaskStatus.PENDING,
        priority=priority,
        seq=1,
        is_blocked=True,
        blocked_reason="x",
        assignee_id=assignee_id,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def task_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(
    task_repo: AsyncMock, workspace_repo: AsyncMock, seq_allocator: AsyncMock
) -> TaskService:
    return TaskService(
        tasks=task_repo,
        members=AsyncMock(),
        workspaces=workspace_repo,
        seq_allocator=seq_allocator,
    )


# ---------- admin path ----------


async def test_admin_default_sort_is_priority(service: TaskService, task_repo: AsyncMock) -> None:
    p = make_principal(role=MemberRole.WORKSPACE_ADMIN)
    task_repo.list_blocks_for_workspace.return_value = (
        [_task(p.workspace_id, title="a")],
        1,
    )
    page = await service.list_blocks(p, skip=0, limit=10)
    assert page.total == 1
    task_repo.list_blocks_for_workspace.assert_awaited_once_with(
        p.workspace_id,
        status=None,
        team_id=None,
        project_id=None,
        assignee_id=None,
        sort=BlocksSort.PRIORITY,
        skip=0,
        limit=10,
    )


async def test_admin_filters_and_sort_forward_to_repo(
    service: TaskService, task_repo: AsyncMock
) -> None:
    """Every filter the admin passes must land on the repo call so
    the SQL narrows the result set, not the service in Python."""
    p = make_principal(role=MemberRole.WORKSPACE_ADMIN)
    team_id = uuid4()
    project_id = uuid4()
    assignee_id = uuid4()
    task_repo.list_blocks_for_workspace.return_value = ([], 0)

    await service.list_blocks(
        p,
        status=TaskStatus.IN_PROGRESS,
        team_id=team_id,
        project_id=project_id,
        assignee_id=assignee_id,
        sort=BlocksSort.NEWEST,
        skip=5,
        limit=5,
    )

    task_repo.list_blocks_for_workspace.assert_awaited_once_with(
        p.workspace_id,
        status=TaskStatus.IN_PROGRESS,
        team_id=team_id,
        project_id=project_id,
        assignee_id=assignee_id,
        sort=BlocksSort.NEWEST,
        skip=5,
        limit=5,
    )


# ---------- non-admin path ----------


async def test_non_admin_assignee_pinned_to_self(
    service: TaskService, task_repo: AsyncMock
) -> None:
    """USER role: any ``assignee_id`` they pass is silently
    overridden with their own member id. Mirrors the kanban's
    visibility rule."""
    p = make_principal(role=MemberRole.WORKSPACE_USER)
    other_id = uuid4()
    task_repo.list_blocks_for_workspace.return_value = ([], 0)

    await service.list_blocks(p, assignee_id=other_id)

    task_repo.list_blocks_for_workspace.assert_awaited_once()
    kwargs = task_repo.list_blocks_for_workspace.await_args.kwargs
    assert kwargs["assignee_id"] == p.member_id
    assert kwargs["assignee_id"] != other_id


async def test_non_admin_other_filters_pass_through(
    service: TaskService, task_repo: AsyncMock
) -> None:
    """Status / team / project filters still apply for non-admins,
    layered on top of the assignee pin."""
    p = make_principal(role=MemberRole.WORKSPACE_USER)
    team_id = uuid4()
    task_repo.list_blocks_for_workspace.return_value = ([], 0)

    await service.list_blocks(p, status=TaskStatus.PENDING, team_id=team_id)

    kwargs = task_repo.list_blocks_for_workspace.await_args.kwargs
    assert kwargs["status"] == TaskStatus.PENDING
    assert kwargs["team_id"] == team_id
    assert kwargs["assignee_id"] == p.member_id
