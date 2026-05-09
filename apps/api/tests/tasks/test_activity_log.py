"""Tests for the auto-recorded activity log on TaskService.

Each mutation must emit exactly one activity row, with the right
event_type and a payload an agent can reason about. These tests run
on mocks of the activity repo to verify the contract; integration with
the SQL layer is exercised via the smoke test against the live api.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.application.tasks.schemas import (
    CreateTaskRequest,
    DelegateTaskRequest,
    RateTaskRequest,
    SetBlockedRequest,
    UpdateTaskLinksRequest,
    UpdateTaskStatusRequest,
)
from app.application.tasks.service import TaskService
from app.domain.entities import Project, Team
from app.domain.enums import ProjectStatus, TaskActivityType, TaskStatus
from tests.tasks.factories import make_principal, make_task


@pytest.fixture
def task_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def members() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def activities() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def projects_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def teams_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def ratings() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(
    task_repo: AsyncMock,
    members: AsyncMock,
    workspace_repo: AsyncMock,
    seq_allocator: AsyncMock,
    activities: AsyncMock,
    projects_repo: AsyncMock,
    teams_repo: AsyncMock,
    ratings: AsyncMock,
) -> TaskService:
    return TaskService(
        tasks=task_repo,
        members=members,
        workspaces=workspace_repo,
        seq_allocator=seq_allocator,
        activities=activities,
        projects=projects_repo,
        team_lookup=teams_repo,
        ratings=ratings,
    )


def _project(workspace_id) -> Project:
    now = datetime.now(UTC)
    return Project(
        id=uuid4(),
        workspace_id=workspace_id,
        name="Test",
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


# ---------- CREATED ----------


async def test_create_emits_created_activity(
    service: TaskService, task_repo: AsyncMock, activities: AsyncMock
) -> None:
    p = make_principal()
    task_repo.create.side_effect = lambda t: t

    await service.create(CreateTaskRequest(title="Pair on the migration"), p)

    activities.create.assert_awaited_once()
    persisted = activities.create.await_args.args[0]
    assert persisted.event_type is TaskActivityType.CREATED
    assert persisted.payload == {"title": "Pair on the migration"}
    assert persisted.actor_member_id == p.member_id


# ---------- STATUS_CHANGED ----------


async def test_status_change_emits_from_to(
    service: TaskService, task_repo: AsyncMock, activities: AsyncMock
) -> None:
    p = make_principal()
    task = make_task(workspace_id=p.workspace_id, status=TaskStatus.PENDING)
    task_repo.get_by_id.return_value = task
    task_repo.update_status.return_value = task

    await service.update_status(task.id, UpdateTaskStatusRequest(status=TaskStatus.IN_PROGRESS), p)

    persisted = activities.create.await_args.args[0]
    assert persisted.event_type is TaskActivityType.STATUS_CHANGED
    assert persisted.payload == {"from": "PENDING", "to": "IN_PROGRESS"}


# ---------- BLOCKED / UNBLOCKED ----------


async def test_block_emits_blocked_with_reason(
    service: TaskService, task_repo: AsyncMock, activities: AsyncMock
) -> None:
    p = make_principal()
    task = make_task(workspace_id=p.workspace_id)
    task_repo.get_by_id.return_value = task
    task_repo.set_blocked.return_value = make_task(
        task_id=task.id,
        workspace_id=p.workspace_id,
        is_blocked=True,
        blocked_reason="missing creds",
    )

    await service.set_blocked(
        task.id, SetBlockedRequest(is_blocked=True, reason="missing creds"), p
    )

    persisted = activities.create.await_args.args[0]
    assert persisted.event_type is TaskActivityType.BLOCKED
    assert persisted.payload == {"reason": "missing creds"}


async def test_unblock_emits_unblocked(
    service: TaskService, task_repo: AsyncMock, activities: AsyncMock
) -> None:
    p = make_principal()
    task = make_task(workspace_id=p.workspace_id, is_blocked=True)
    task_repo.get_by_id.return_value = task
    task_repo.set_blocked.return_value = make_task(task_id=task.id, workspace_id=p.workspace_id)

    await service.set_blocked(task.id, SetBlockedRequest(is_blocked=False), p)

    persisted = activities.create.await_args.args[0]
    assert persisted.event_type is TaskActivityType.UNBLOCKED
    assert persisted.payload == {}


# ---------- DELEGATED ----------


async def test_delegate_emits_delegated(
    service: TaskService,
    task_repo: AsyncMock,
    members: AsyncMock,
    activities: AsyncMock,
) -> None:
    p = make_principal(priority=1)
    task = make_task(workspace_id=p.workspace_id)
    target_id = uuid4()

    # Target is a real member in the same workspace, lower priority.
    from app.domain.entities import Member
    from app.domain.enums import MemberType

    members.get_by_id.return_value = Member(
        id=target_id,
        workspace_id=p.workspace_id,
        type=MemberType.AGENT,
        name="bot",
        priority=5,
        email=None,
    )
    task_repo.get_by_id.return_value = task
    task_repo.assign.return_value = make_task(
        task_id=task.id, workspace_id=p.workspace_id, assignee_id=target_id
    )

    await service.delegate(task.id, DelegateTaskRequest(member_id=target_id), p)

    persisted = activities.create.await_args.args[0]
    assert persisted.event_type is TaskActivityType.DELEGATED
    assert persisted.payload == {"from": None, "to": str(target_id)}


# ---------- PROJECT_CHANGED / TEAM_CHANGED ----------


async def test_update_links_emits_project_and_team_changes(
    service: TaskService,
    task_repo: AsyncMock,
    projects_repo: AsyncMock,
    teams_repo: AsyncMock,
    activities: AsyncMock,
) -> None:
    """One event per dimension that actually changed. Two events when
    both project and team move at once."""
    p = make_principal()
    task = make_task(workspace_id=p.workspace_id)  # project_id=None, team_id=None
    project = _project(p.workspace_id)
    team = _team(p.workspace_id)
    projects_repo.get_by_id.return_value = project
    teams_repo.get_by_id.return_value = team
    task_repo.get_by_id.return_value = task
    task_repo.update_links.return_value = make_task(
        task_id=task.id,
        workspace_id=p.workspace_id,
    )
    # Hand-build the moved task so the service sees a delta.
    moved = task_repo.update_links.return_value
    moved.project_id = project.id
    moved.team_id = team.id

    await service.update_links(
        task.id,
        UpdateTaskLinksRequest(project_id=project.id, team_id=team.id),
        p,
    )

    assert activities.create.await_count == 2
    types = {call.args[0].event_type for call in activities.create.await_args_list}
    assert TaskActivityType.PROJECT_CHANGED in types
    assert TaskActivityType.TEAM_CHANGED in types


async def test_update_links_no_change_emits_nothing(
    service: TaskService,
    task_repo: AsyncMock,
    projects_repo: AsyncMock,
    activities: AsyncMock,
) -> None:
    """If project_id is omitted from the body and the link doesn't
    change, no activity row should be written."""
    p = make_principal()
    task = make_task(workspace_id=p.workspace_id)
    task_repo.get_by_id.return_value = task
    task_repo.update_links.return_value = task

    await service.update_links(task.id, UpdateTaskLinksRequest(), p)

    activities.create.assert_not_called()


# ---------- RATED ----------


async def test_rate_emits_rated(
    service: TaskService,
    task_repo: AsyncMock,
    ratings: AsyncMock,
    activities: AsyncMock,
) -> None:
    p = make_principal()
    task = make_task(
        workspace_id=p.workspace_id,
        status=TaskStatus.DONE,
        created_by_id=p.member_id,
    )
    task_repo.get_by_id.return_value = task
    ratings.get_for_task.return_value = None
    ratings.create.side_effect = lambda r: r

    await service.rate_task(task.id, RateTaskRequest(score=85, feedback="solid"), p)

    # Two repo writes: ratings.create + activities.create. Pick the
    # activity one out.
    rated_activity = next(
        call.args[0]
        for call in activities.create.await_args_list
        if call.args[0].event_type is TaskActivityType.RATED
    )
    assert rated_activity.payload == {"score": 85, "feedback": "solid"}
