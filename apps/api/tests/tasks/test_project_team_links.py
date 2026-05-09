"""Tests for the Workspace -> Project -> Task -> Team links on tasks.

Contract:
- Creating a task with a project_id / team_id from a different workspace
  raises ProjectNotFoundError / TeamNotFoundError (router maps to 422).
- update_links can move a task between projects and teams; passing null
  clears the link, omitting the field leaves it untouched.
- list_for_workspace passes through project_id / team_id filters.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.application.tasks.schemas import (
    CreateTaskRequest,
    UpdateTaskLinksRequest,
)
from app.application.tasks.service import TaskService
from app.domain.entities import Project, Team
from app.domain.enums import ProjectStatus, TaskStatus
from app.domain.exceptions import ProjectNotFoundError, TeamNotFoundError
from tests.tasks.factories import make_principal, make_task


def _project(workspace_id) -> Project:
    now = datetime.now(UTC)
    return Project(
        id=uuid4(),
        workspace_id=workspace_id,
        name="Test project",
        description=None,
        status=ProjectStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )


def _team(workspace_id) -> Team:
    now = datetime.now(UTC)
    return Team(
        id=uuid4(),
        workspace_id=workspace_id,
        name="Backend",
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def task_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def members() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def projects_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def teams_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(
    task_repo: AsyncMock,
    members: AsyncMock,
    workspace_repo: AsyncMock,
    seq_allocator: AsyncMock,
    projects_repo: AsyncMock,
    teams_repo: AsyncMock,
) -> TaskService:
    return TaskService(
        tasks=task_repo,
        members=members,
        workspaces=workspace_repo,
        seq_allocator=seq_allocator,
        projects=projects_repo,
        team_lookup=teams_repo,
    )


# ---------- create with project + team ----------


async def test_create_persists_project_and_team(
    service: TaskService,
    task_repo: AsyncMock,
    projects_repo: AsyncMock,
    teams_repo: AsyncMock,
) -> None:
    p = make_principal()
    project = _project(p.workspace_id)
    team = _team(p.workspace_id)
    projects_repo.get_by_id.return_value = project
    teams_repo.get_by_id.return_value = team
    task_repo.create.side_effect = lambda t: t

    response = await service.create(
        CreateTaskRequest(
            title="Wire up dashboard",
            project_id=project.id,
            team_id=team.id,
        ),
        p,
    )
    assert response.project_id == project.id
    assert response.team_id == team.id

    persisted = task_repo.create.await_args.args[0]
    assert persisted.project_id == project.id
    assert persisted.team_id == team.id
    assert persisted.status is TaskStatus.PENDING


async def test_create_404s_for_cross_tenant_project(
    service: TaskService, projects_repo: AsyncMock, task_repo: AsyncMock
) -> None:
    p = make_principal()
    projects_repo.get_by_id.return_value = _project(uuid4())  # other workspace
    with pytest.raises(ProjectNotFoundError):
        await service.create(CreateTaskRequest(title="bad project", project_id=uuid4()), p)
    task_repo.create.assert_not_called()


async def test_create_404s_for_cross_tenant_team(
    service: TaskService,
    teams_repo: AsyncMock,
    task_repo: AsyncMock,
) -> None:
    p = make_principal()
    teams_repo.get_by_id.return_value = _team(uuid4())  # other workspace
    with pytest.raises(TeamNotFoundError):
        await service.create(CreateTaskRequest(title="bad team", team_id=uuid4()), p)
    task_repo.create.assert_not_called()


# ---------- update_links ----------


async def test_update_links_sets_project_and_team(
    service: TaskService,
    task_repo: AsyncMock,
    projects_repo: AsyncMock,
    teams_repo: AsyncMock,
) -> None:
    p = make_principal()
    task = make_task(workspace_id=p.workspace_id)
    project = _project(p.workspace_id)
    team = _team(p.workspace_id)
    task_repo.get_by_id.return_value = task
    projects_repo.get_by_id.return_value = project
    teams_repo.get_by_id.return_value = team
    task_repo.update_links.return_value = make_task(task_id=task.id, workspace_id=p.workspace_id)

    await service.update_links(
        task.id,
        UpdateTaskLinksRequest(project_id=project.id, team_id=team.id),
        p,
    )

    task_repo.update_links.assert_awaited_once_with(
        task.id,
        project_id=project.id,
        team_id=team.id,
        clear_project=False,
        clear_team=False,
    )


async def test_update_links_explicit_null_clears(
    service: TaskService, task_repo: AsyncMock
) -> None:
    """Passing project_id=null in the body must clear, not leave it
    untouched."""
    p = make_principal()
    task = make_task(workspace_id=p.workspace_id)
    task_repo.get_by_id.return_value = task
    task_repo.update_links.return_value = make_task(task_id=task.id, workspace_id=p.workspace_id)

    request = UpdateTaskLinksRequest.model_validate({"project_id": None})
    await service.update_links(task.id, request, p)

    _, kwargs = task_repo.update_links.await_args
    assert kwargs["clear_project"] is True
    assert kwargs["clear_team"] is False


async def test_list_passes_project_filter(service: TaskService, task_repo: AsyncMock) -> None:
    p = make_principal()
    project_id = uuid4()
    task_repo.list_by_workspace.return_value = []
    await service.list_for_workspace(p, project_id=project_id)
    task_repo.list_by_workspace.assert_awaited_once_with(
        p.workspace_id,
        status=None,
        blocked_only=False,
        project_id=project_id,
        team_id=None,
        assignee_id=None,
    )
