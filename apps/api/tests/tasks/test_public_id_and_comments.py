"""Tests for the human-readable task id (`DEVOPS-001`) and the
task-comments thread.

Contract:

- On task create, the service asks the seq allocator for an atomic
  (seq, prefix) pair. The response carries `seq` and `public_id`
  computed as ``f"{prefix}-{seq:03d}"``.
- Two simultaneous creates never collide on (workspace_id, seq) — that
  guarantee lives in the SQL UPDATE...RETURNING in
  WorkspaceTaskSeqRepository, so the service test mocks it.
- Comments are workspace-scoped: an arbitrary member can post + read,
  but only on tasks within their own workspace. Tenant-isolation 404
  for cross-tenant access (same shape as a missing task).
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.application.tasks.schemas import (
    CreateCommentRequest,
    CreateTaskRequest,
)
from app.application.tasks.service import TaskService
from app.domain.entities import TaskComment
from app.domain.exceptions import TaskNotFoundError
from tests.tasks.factories import make_principal, make_task


@pytest.fixture
def task_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def members() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def comments() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(
    task_repo: AsyncMock,
    members: AsyncMock,
    workspace_repo: AsyncMock,
    seq_allocator: AsyncMock,
    comments: AsyncMock,
) -> TaskService:
    return TaskService(
        tasks=task_repo,
        members=members,
        workspaces=workspace_repo,
        seq_allocator=seq_allocator,
        comments=comments,
    )


# ---------- public_id ----------


async def test_create_assigns_seq_and_public_id(
    service: TaskService,
    task_repo: AsyncMock,
    seq_allocator: AsyncMock,
) -> None:
    p = make_principal()
    seq_allocator.allocate_next_task_seq.return_value = (7, "DEVOPS")
    task_repo.create.side_effect = lambda t: t

    response = await service.create(CreateTaskRequest(title="Bump CI image"), p)

    seq_allocator.allocate_next_task_seq.assert_awaited_once_with(p.workspace_id)
    persisted = task_repo.create.await_args.args[0]
    assert persisted.seq == 7
    assert response.seq == 7
    assert response.public_id == "DEVOPS-007"


async def test_public_id_zero_pads_low_seq(
    service: TaskService,
    task_repo: AsyncMock,
    seq_allocator: AsyncMock,
) -> None:
    p = make_principal()
    seq_allocator.allocate_next_task_seq.return_value = (1, "ACME")
    task_repo.create.side_effect = lambda t: t
    response = await service.create(CreateTaskRequest(title="x"), p)
    assert response.public_id == "ACME-001"


async def test_public_id_stays_for_existing_tasks(
    service: TaskService,
    task_repo: AsyncMock,
    workspace_repo: AsyncMock,
) -> None:
    """get_by_id must rebuild public_id from the workspace prefix —
    not stash the prefix on the task itself, so workspace renames
    propagate without a backfill."""
    p = make_principal()
    task = make_task(workspace_id=p.workspace_id, seq=42)
    task_repo.get_by_id.return_value = task

    # Custom prefix on the workspace stub.
    from app.domain.entities import Workspace

    workspace_repo.get_by_id.return_value = Workspace(
        id=p.workspace_id,
        name="Renamed",
        slug="renamed",
        task_prefix="RENAME",
        next_task_seq=43,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    response = await service.get_by_id(task.id, p)
    assert response.public_id == "RENAME-042"


# ---------- comments ----------


async def test_post_comment_attaches_principal_as_author(
    service: TaskService,
    task_repo: AsyncMock,
    comments: AsyncMock,
    members: AsyncMock,
) -> None:
    p = make_principal()
    task = make_task(workspace_id=p.workspace_id)
    task_repo.get_by_id.return_value = task

    captured: dict = {}

    async def _create(comment: TaskComment) -> TaskComment:
        captured["comment"] = comment
        return comment

    comments.create.side_effect = _create

    members.get_by_id.return_value = type("M", (), {"name": "Jordi"})()

    response = await service.post_comment(
        task.id,
        CreateCommentRequest(body="looks good to me"),
        p,
    )

    persisted = captured["comment"]
    assert persisted.task_id == task.id
    assert persisted.author_member_id == p.member_id
    assert persisted.body == "looks good to me"
    assert response.body == "looks good to me"
    assert response.author_member_id == p.member_id
    assert response.author_name == "Jordi"


async def test_post_comment_404s_for_other_workspace(
    service: TaskService, task_repo: AsyncMock, comments: AsyncMock
) -> None:
    """Cross-tenant comment attempts surface as 404 — same shape as a
    truly-missing task so the existence isn't leaked."""
    p = make_principal()
    task_repo.get_by_id.return_value = make_task(workspace_id=uuid4())
    with pytest.raises(TaskNotFoundError):
        await service.post_comment(uuid4(), CreateCommentRequest(body="hi"), p)
    comments.create.assert_not_called()


async def test_list_comments_orders_oldest_first(
    service: TaskService,
    task_repo: AsyncMock,
    comments: AsyncMock,
    members: AsyncMock,
) -> None:
    """The service relies on the repo to order; we just verify the call
    boundary and that author resolution happens once per comment."""
    p = make_principal()
    task = make_task(workspace_id=p.workspace_id)
    task_repo.get_by_id.return_value = task

    a, b = uuid4(), uuid4()
    now = datetime.now(UTC)
    comments.list_for_task.return_value = [
        TaskComment(id=uuid4(), task_id=task.id, author_member_id=a, body="first", created_at=now),
        TaskComment(id=uuid4(), task_id=task.id, author_member_id=b, body="second", created_at=now),
    ]

    member_a = type("M", (), {"name": "Alice"})()
    member_b = type("M", (), {"name": "Bot"})()
    members.get_by_id.side_effect = [member_a, member_b]

    out = await service.list_comments(task.id, p)
    assert [c.body for c in out] == ["first", "second"]
    assert out[0].author_name == "Alice"
    assert out[1].author_name == "Bot"


async def test_list_comments_handles_deleted_author(
    service: TaskService,
    task_repo: AsyncMock,
    comments: AsyncMock,
    members: AsyncMock,
) -> None:
    p = make_principal()
    task = make_task(workspace_id=p.workspace_id)
    task_repo.get_by_id.return_value = task
    comments.list_for_task.return_value = [
        TaskComment(
            id=uuid4(),
            task_id=task.id,
            # FK SET NULL once the author was removed.
            author_member_id=None,
            body="left by a deleted account",
            created_at=datetime.now(UTC),
        )
    ]
    out = await service.list_comments(task.id, p)
    assert out[0].author_member_id is None
    assert out[0].author_name is None
    members.get_by_id.assert_not_called()
