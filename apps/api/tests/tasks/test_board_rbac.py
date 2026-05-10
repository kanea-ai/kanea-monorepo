"""Section 2 RBAC contract for the kanban list endpoint.

- Workspace OWNER / ADMIN: see all tasks. ?assignee_id filter is honored.
- Other principals (MEMBER role): forced to assignee_id = self,
  regardless of any ?assignee_id passed in the query string.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.application.tasks.service import TaskService
from app.domain.enums import MemberRole, TaskStatus
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


async def test_admin_sees_all_when_no_filter(service: TaskService, task_repo: AsyncMock) -> None:
    p = make_principal(role=MemberRole.WORKSPACE_ADMIN)
    task_repo.list_by_workspace.return_value = []
    await service.list_for_workspace(p)
    _, kwargs = task_repo.list_by_workspace.await_args
    assert kwargs["assignee_id"] is None  # no scoping


async def test_admin_can_filter_by_assignee(service: TaskService, task_repo: AsyncMock) -> None:
    p = make_principal(role=MemberRole.WORKSPACE_OWNER)
    target_id = uuid4()
    task_repo.list_by_workspace.return_value = []
    await service.list_for_workspace(p, assignee_id=target_id)
    _, kwargs = task_repo.list_by_workspace.await_args
    assert kwargs["assignee_id"] == target_id


async def test_non_admin_is_forced_to_self(service: TaskService, task_repo: AsyncMock) -> None:
    p = make_principal(role=MemberRole.WORKSPACE_USER)
    task_repo.list_by_workspace.return_value = []
    await service.list_for_workspace(p)
    _, kwargs = task_repo.list_by_workspace.await_args
    assert kwargs["assignee_id"] == p.member_id


async def test_non_admin_assignee_query_is_silently_overridden(
    service: TaskService, task_repo: AsyncMock
) -> None:
    """Non-admin tries to spoof another assignee — server forces back
    to self. No 403, just silent narrow."""
    p = make_principal(role=MemberRole.WORKSPACE_USER)
    task_repo.list_by_workspace.return_value = []
    await service.list_for_workspace(p, assignee_id=uuid4())
    _, kwargs = task_repo.list_by_workspace.await_args
    assert kwargs["assignee_id"] == p.member_id


async def test_non_admin_can_still_use_other_filters(
    service: TaskService, task_repo: AsyncMock
) -> None:
    """Non-admin keeps every other filter — only assignee is locked."""
    p = make_principal(role=MemberRole.WORKSPACE_USER)
    project_id = uuid4()
    task_repo.list_by_workspace.return_value = [
        make_task(workspace_id=p.workspace_id, status=TaskStatus.IN_PROGRESS)
    ]
    await service.list_for_workspace(p, status=TaskStatus.IN_PROGRESS, project_id=project_id)
    _, kwargs = task_repo.list_by_workspace.await_args
    assert kwargs["status"] is TaskStatus.IN_PROGRESS
    assert kwargs["project_id"] == project_id
    assert kwargs["assignee_id"] == p.member_id
