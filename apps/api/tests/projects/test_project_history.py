"""Tests for the AI-facing project history bundle.

The contract: GET /projects/{id}/history returns a single payload an
agent can reason about — project metadata, summary aggregates, and
per-task history (metadata + activities + comments + rating).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.application.projects.service import ProjectService
from app.domain.entities import (
    Project,
    TaskActivity,
    TaskComment,
    TaskRating,
    Workspace,
)
from app.domain.enums import ProjectStatus, TaskActivityType, TaskStatus
from app.domain.exceptions import ProjectNotFoundError
from tests.tasks.factories import make_principal, make_task


def _project(workspace_id) -> Project:
    now = datetime.now(UTC)
    return Project(
        id=uuid4(),
        workspace_id=workspace_id,
        name="Launch website",
        description="Q3 push",
        status=ProjectStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )


def _ws(workspace_id, prefix="ACME") -> Workspace:
    now = datetime.now(UTC)
    return Workspace(
        id=workspace_id,
        name="Acme",
        slug="acme",
        task_prefix=prefix,
        next_task_seq=1,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def projects_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def tasks() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def activities() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def comments() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def ratings() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def members() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def workspaces_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(
    projects_repo: AsyncMock,
    tasks: AsyncMock,
    activities: AsyncMock,
    comments: AsyncMock,
    ratings: AsyncMock,
    members: AsyncMock,
    workspaces_repo: AsyncMock,
) -> ProjectService:
    return ProjectService(
        projects=projects_repo,
        tasks=tasks,
        activities=activities,
        comments=comments,
        ratings=ratings,
        members=members,
        workspaces=workspaces_repo,
    )


async def test_history_404s_for_other_workspace(
    service: ProjectService, projects_repo: AsyncMock
) -> None:
    p = make_principal()
    projects_repo.get_by_id.return_value = _project(uuid4())  # other ws
    with pytest.raises(ProjectNotFoundError):
        await service.compute_history(uuid4(), p)


async def test_history_bundles_tasks_activities_comments_ratings(
    service: ProjectService,
    projects_repo: AsyncMock,
    tasks: AsyncMock,
    activities: AsyncMock,
    comments: AsyncMock,
    ratings: AsyncMock,
    workspaces_repo: AsyncMock,
) -> None:
    p = make_principal()
    project = _project(p.workspace_id)
    projects_repo.get_by_id.return_value = project
    workspaces_repo.get_by_id.return_value = _ws(p.workspace_id)

    # One DONE task with full lifecycle: rated, with one activity + one comment.
    done_at = datetime.now(UTC)
    task = make_task(workspace_id=p.workspace_id, seq=1, status=TaskStatus.DONE)
    task.completed_at = done_at
    task.created_at = done_at - timedelta(hours=2)
    task.tokens_used = 1234

    tasks.list_by_workspace.return_value = [task]
    activities.list_for_task.return_value = [
        TaskActivity(
            id=uuid4(),
            task_id=task.id,
            actor_member_id=None,
            event_type=TaskActivityType.STATUS_CHANGED,
            payload={"from": "PENDING", "to": "DONE"},
            created_at=done_at,
        )
    ]
    comments.list_for_task.return_value = [
        TaskComment(
            id=uuid4(),
            task_id=task.id,
            author_member_id=None,
            body="finished early",
            created_at=done_at,
        )
    ]
    ratings.get_for_task.return_value = TaskRating(
        id=uuid4(),
        task_id=task.id,
        rated_by_id=p.member_id,
        rated_member_id=None,
        score=92,
        feedback="solid",
        created_at=done_at,
        updated_at=done_at,
    )

    history = await service.compute_history(project.id, p)

    assert history.project.id == project.id
    assert history.summary.total_tasks == 1
    assert history.summary.by_status["DONE"] == 1
    assert history.summary.total_tokens_used == 1234
    assert history.summary.rated_count == 1
    assert history.summary.avg_rating == 92.0
    assert history.summary.avg_resolution_seconds is not None
    # Two hours +/- a few seconds.
    assert 7100 < history.summary.avg_resolution_seconds < 7300

    [t] = history.tasks
    assert t.public_id == "ACME-001"
    assert t.tokens_used == 1234
    assert t.rating is not None
    assert t.rating.score == 92
    assert len(t.activities) == 1
    assert t.activities[0].event_type is TaskActivityType.STATUS_CHANGED
    assert len(t.comments) == 1
    assert t.comments[0].body == "finished early"


async def test_history_summary_handles_empty_project(
    service: ProjectService,
    projects_repo: AsyncMock,
    tasks: AsyncMock,
    workspaces_repo: AsyncMock,
) -> None:
    """Empty project: zero counts, no avg numbers."""
    p = make_principal()
    project = _project(p.workspace_id)
    projects_repo.get_by_id.return_value = project
    workspaces_repo.get_by_id.return_value = _ws(p.workspace_id)
    tasks.list_by_workspace.return_value = []

    history = await service.compute_history(project.id, p)

    assert history.summary.total_tasks == 0
    assert history.summary.avg_resolution_seconds is None
    assert history.summary.avg_rating is None
    assert history.summary.total_tokens_used == 0
    assert history.tasks == []
