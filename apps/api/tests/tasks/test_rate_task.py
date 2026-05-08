"""rate_task service tests. Contract:

- only the task creator can rate (RatingForbiddenError otherwise)
- task must be DONE (TaskNotInDoneStateError otherwise)
- one rating per task (TaskAlreadyRatedError on second attempt)
- rating's rated_member_id is the task's assignee at rating time
- works across workspaces only via tenant-isolation: 404 for other ws
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.application.tasks.schemas import RateTaskRequest
from app.application.tasks.service import TaskService
from app.domain.entities import Task, TaskRating
from app.domain.enums import TaskStatus
from app.domain.exceptions import (
    RatingForbiddenError,
    TaskAlreadyRatedError,
    TaskNotFoundError,
    TaskNotInDoneStateError,
)
from tests.tasks.factories import make_principal


def _task(
    *, status=TaskStatus.DONE, created_by_id=None, assignee_id=None, workspace_id=None
) -> Task:
    return Task(
        id=uuid4(),
        workspace_id=workspace_id or uuid4(),
        created_by_id=created_by_id or uuid4(),
        title="Some work",
        status=status,
        priority=3,
        description=None,
        assignee_id=assignee_id,
        due_at=None,
        blocked_reason=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


@pytest.fixture
def task_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def members() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def ratings() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(task_repo: AsyncMock, members: AsyncMock, ratings: AsyncMock) -> TaskService:
    return TaskService(tasks=task_repo, members=members, ratings=ratings)


async def test_creator_can_rate_done_task(
    service: TaskService, task_repo: AsyncMock, ratings: AsyncMock
) -> None:
    p = make_principal()
    agent_id = uuid4()
    task = _task(workspace_id=p.workspace_id, created_by_id=p.member_id, assignee_id=agent_id)
    task_repo.get_by_id.return_value = task
    ratings.get_for_task.return_value = None
    ratings.create.side_effect = lambda r: r

    response = await service.rate_task(task.id, RateTaskRequest(score=85, feedback="solid"), p)

    assert response.score == 85
    assert response.feedback == "solid"
    assert response.rated_member_id == agent_id

    ratings.create.assert_awaited_once()
    persisted: TaskRating = ratings.create.await_args.args[0]
    assert persisted.task_id == task.id
    assert persisted.rated_by_id == p.member_id
    assert persisted.rated_member_id == agent_id


async def test_rate_rejected_for_non_creator(service: TaskService, task_repo: AsyncMock) -> None:
    """Assignees can't self-rate; peers can't rate each other's work.
    Only the task issuer rates."""
    p = make_principal()
    task_repo.get_by_id.return_value = _task(workspace_id=p.workspace_id, created_by_id=uuid4())
    with pytest.raises(RatingForbiddenError):
        await service.rate_task(uuid4(), RateTaskRequest(score=50), p)


async def test_rate_rejected_when_task_not_done(service: TaskService, task_repo: AsyncMock) -> None:
    p = make_principal()
    task_repo.get_by_id.return_value = _task(
        workspace_id=p.workspace_id,
        created_by_id=p.member_id,
        status=TaskStatus.IN_PROGRESS,
    )
    with pytest.raises(TaskNotInDoneStateError):
        await service.rate_task(uuid4(), RateTaskRequest(score=50), p)


async def test_rate_rejected_when_already_rated(
    service: TaskService, task_repo: AsyncMock, ratings: AsyncMock
) -> None:
    p = make_principal()
    task = _task(workspace_id=p.workspace_id, created_by_id=p.member_id)
    task_repo.get_by_id.return_value = task
    ratings.get_for_task.return_value = TaskRating(
        id=uuid4(),
        task_id=task.id,
        rated_by_id=p.member_id,
        rated_member_id=uuid4(),
        score=70,
        feedback=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    with pytest.raises(TaskAlreadyRatedError):
        await service.rate_task(task.id, RateTaskRequest(score=80), p)


async def test_rate_404s_for_other_workspace_task(
    service: TaskService, task_repo: AsyncMock
) -> None:
    p = make_principal()
    task_repo.get_by_id.return_value = _task(workspace_id=uuid4())  # other workspace
    with pytest.raises(TaskNotFoundError):
        await service.rate_task(uuid4(), RateTaskRequest(score=50), p)


async def test_rate_404s_when_task_missing(service: TaskService, task_repo: AsyncMock) -> None:
    p = make_principal()
    task_repo.get_by_id.return_value = None
    with pytest.raises(TaskNotFoundError):
        await service.rate_task(uuid4(), RateTaskRequest(score=50), p)
