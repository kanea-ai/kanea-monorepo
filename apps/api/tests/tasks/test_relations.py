"""Tests for task relations.

Contract:
- A task can be linked to another task in the same workspace via one
  of four directed relation types: BLOCKS, MITIGATES, DUPLICATES,
  RELATES_TO. RELATES_TO is symmetric — the inverse views
  (blocked_by / mitigated_by / duplicated_by) are computed from the
  same row stored source -> target.
- Self-links are rejected (TaskRelationSelfLinkError -> 400).
- A duplicate (source, target, type) tuple raises
  TaskRelationAlreadyExistsError -> 409.
- Cross-tenant counterparts surface as 404 (TaskNotFoundError) — the
  same shape as a missing task so existence isn't leaked.
- Listing groups the relations into seven UI buckets.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_principal, get_task_service
from app.application.tasks.schemas import CreateRelationRequest
from app.application.tasks.service import TaskService
from app.domain.entities import TaskRelation
from app.domain.enums import TaskRelationType
from app.domain.exceptions import (
    TaskNotFoundError,
    TaskRelationAlreadyExistsError,
    TaskRelationNotFoundError,
    TaskRelationSelfLinkError,
)
from app.main import app
from tests.tasks.factories import make_principal, make_task


def _principal_for(task_workspace_id: UUID) -> AsyncMock:
    """Helper to build a principal pinned to a given workspace."""
    return make_principal(workspace_id=task_workspace_id, priority=1)


@pytest.fixture
def task_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def member_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def relations() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(
    task_repo: AsyncMock,
    member_repo: AsyncMock,
    workspace_repo: AsyncMock,
    seq_allocator: AsyncMock,
    relations: AsyncMock,
) -> TaskService:
    return TaskService(
        tasks=task_repo,
        members=member_repo,
        workspaces=workspace_repo,
        seq_allocator=seq_allocator,
        relations=relations,
    )


# ---------- create_relation ----------


async def test_self_link_is_rejected(
    service: TaskService, task_repo: AsyncMock, relations: AsyncMock
) -> None:
    p = _principal_for(uuid4())
    task_id = uuid4()
    with pytest.raises(TaskRelationSelfLinkError):
        await service.create_relation(
            task_id,
            CreateRelationRequest(
                relation_type=TaskRelationType.RELATES_TO,
                target_task_id=task_id,
            ),
            p,
        )
    relations.create.assert_not_called()
    task_repo.get_by_id.assert_not_called()


async def test_create_404s_when_target_in_other_workspace(
    service: TaskService, task_repo: AsyncMock, relations: AsyncMock
) -> None:
    p = make_principal()
    source = make_task(workspace_id=p.workspace_id)
    other = make_task(workspace_id=uuid4())  # different workspace

    # Service calls _load_task twice — first for source (ok), then target.
    task_repo.get_by_id.side_effect = [source, other]

    with pytest.raises(TaskNotFoundError):
        await service.create_relation(
            source.id,
            CreateRelationRequest(
                relation_type=TaskRelationType.BLOCKS,
                target_task_id=other.id,
            ),
            p,
        )
    relations.create.assert_not_called()


async def test_create_rejects_duplicate(
    service: TaskService, task_repo: AsyncMock, relations: AsyncMock
) -> None:
    p = make_principal()
    source = make_task(workspace_id=p.workspace_id)
    target = make_task(workspace_id=p.workspace_id)
    task_repo.get_by_id.side_effect = [source, target]

    relations.get_existing.return_value = TaskRelation(
        id=uuid4(),
        source_task_id=source.id,
        target_task_id=target.id,
        relation_type=TaskRelationType.BLOCKS,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    with pytest.raises(TaskRelationAlreadyExistsError):
        await service.create_relation(
            source.id,
            CreateRelationRequest(
                relation_type=TaskRelationType.BLOCKS,
                target_task_id=target.id,
            ),
            p,
        )
    relations.create.assert_not_called()


async def test_create_persists_relation(
    service: TaskService, task_repo: AsyncMock, relations: AsyncMock
) -> None:
    p = make_principal()
    source = make_task(workspace_id=p.workspace_id)
    target = make_task(workspace_id=p.workspace_id)
    task_repo.get_by_id.side_effect = [source, target]
    relations.get_existing.return_value = None
    relations.create.side_effect = lambda r: r

    await service.create_relation(
        source.id,
        CreateRelationRequest(
            relation_type=TaskRelationType.MITIGATES,
            target_task_id=target.id,
        ),
        p,
    )
    relations.create.assert_awaited_once()
    persisted: TaskRelation = relations.create.await_args.args[0]
    assert persisted.source_task_id == source.id
    assert persisted.target_task_id == target.id
    assert persisted.relation_type is TaskRelationType.MITIGATES


# ---------- delete_relation ----------


async def test_delete_unknown_relation_404s(service: TaskService, relations: AsyncMock) -> None:
    p = make_principal()
    relations.get_by_id.return_value = None
    with pytest.raises(TaskRelationNotFoundError):
        await service.delete_relation(uuid4(), uuid4(), p)


async def test_delete_relation_anchored_to_other_task_404s(
    service: TaskService, relations: AsyncMock
) -> None:
    """The route's task_id must be one end of the relation. If you ask
    to delete relation X via task A but the relation is between B and
    C, surface 404 — never silently delete from the wrong handle."""
    p = make_principal()
    relations.get_by_id.return_value = TaskRelation(
        id=uuid4(),
        source_task_id=uuid4(),
        target_task_id=uuid4(),
        relation_type=TaskRelationType.BLOCKS,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    with pytest.raises(TaskRelationNotFoundError):
        await service.delete_relation(uuid4(), uuid4(), p)


async def test_delete_relation_happy_path(
    service: TaskService,
    task_repo: AsyncMock,
    relations: AsyncMock,
) -> None:
    p = make_principal()
    source = make_task(workspace_id=p.workspace_id)
    relation_id = uuid4()
    relations.get_by_id.return_value = TaskRelation(
        id=relation_id,
        source_task_id=source.id,
        target_task_id=uuid4(),
        relation_type=TaskRelationType.BLOCKS,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    task_repo.get_by_id.return_value = source

    await service.delete_relation(source.id, relation_id, p)
    relations.delete.assert_awaited_once_with(relation_id)


# ---------- list_relations / grouping ----------


async def test_list_groups_into_seven_buckets(
    service: TaskService,
    task_repo: AsyncMock,
    relations: AsyncMock,
) -> None:
    p = make_principal()
    me = make_task(workspace_id=p.workspace_id, seq=1)

    # Five counterpart tasks, one for each relation we'll exercise.
    blocker = make_task(workspace_id=p.workspace_id, seq=2)  # blocks me
    blocked_by_me = make_task(workspace_id=p.workspace_id, seq=3)  # me blocks
    mitigates_me = make_task(workspace_id=p.workspace_id, seq=4)  # mitigates me
    dup_target = make_task(workspace_id=p.workspace_id, seq=5)  # me duplicates
    related = make_task(workspace_id=p.workspace_id, seq=6)  # symmetric

    task_repo.get_by_id.return_value = me
    task_repo.list_by_ids.return_value = [
        blocker,
        blocked_by_me,
        mitigates_me,
        dup_target,
        related,
    ]

    relations.list_for_task.return_value = [
        TaskRelation(
            id=uuid4(),
            source_task_id=blocker.id,
            target_task_id=me.id,
            relation_type=TaskRelationType.BLOCKS,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ),
        TaskRelation(
            id=uuid4(),
            source_task_id=me.id,
            target_task_id=blocked_by_me.id,
            relation_type=TaskRelationType.BLOCKS,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ),
        TaskRelation(
            id=uuid4(),
            source_task_id=mitigates_me.id,
            target_task_id=me.id,
            relation_type=TaskRelationType.MITIGATES,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ),
        TaskRelation(
            id=uuid4(),
            source_task_id=me.id,
            target_task_id=dup_target.id,
            relation_type=TaskRelationType.DUPLICATES,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ),
        # Symmetric — exercise both directions to confirm we don't
        # double-bucket.
        TaskRelation(
            id=uuid4(),
            source_task_id=related.id,
            target_task_id=me.id,
            relation_type=TaskRelationType.RELATES_TO,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ),
    ]

    out = await service.list_relations(me.id, p)

    assert [item.task_id for item in out.blocks] == [blocked_by_me.id]
    assert [item.task_id for item in out.blocked_by] == [blocker.id]
    assert [item.task_id for item in out.mitigated_by] == [mitigates_me.id]
    assert [item.task_id for item in out.duplicates] == [dup_target.id]
    assert [item.task_id for item in out.relates_to] == [related.id]
    assert out.mitigates == []
    assert out.duplicated_by == []

    # Public ids are derived from prefix + zero-padded seq.
    assert out.blocks[0].public_id == "TASK-003"
    assert out.blocked_by[0].public_id == "TASK-002"


async def test_list_drops_cross_tenant_counterparts(
    service: TaskService,
    task_repo: AsyncMock,
    relations: AsyncMock,
) -> None:
    """Defence in depth: even if a relation row somehow points at a
    task in another workspace, we never surface it."""
    p = make_principal()
    me = make_task(workspace_id=p.workspace_id)
    other = make_task(workspace_id=uuid4())

    task_repo.get_by_id.return_value = me
    task_repo.list_by_ids.return_value = [other]
    relations.list_for_task.return_value = [
        TaskRelation(
            id=uuid4(),
            source_task_id=me.id,
            target_task_id=other.id,
            relation_type=TaskRelationType.BLOCKS,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    ]
    out = await service.list_relations(me.id, p)
    assert out.blocks == []


# ---------- router ----------


@pytest.fixture
def task_service_mock() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def principal_obj():
    return make_principal()


@pytest.fixture
def client(task_service_mock: AsyncMock, principal_obj) -> Iterator[TestClient]:
    app.dependency_overrides[get_task_service] = lambda: task_service_mock
    app.dependency_overrides[get_current_principal] = lambda: principal_obj
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_create_relation_returns_201(client: TestClient, task_service_mock: AsyncMock) -> None:
    task_service_mock.create_relation.return_value = TaskRelation(
        id=uuid4(),
        source_task_id=uuid4(),
        target_task_id=uuid4(),
        relation_type=TaskRelationType.BLOCKS,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    response = client.post(
        f"/api/v1/tasks/{uuid4()}/relations",
        json={"relation_type": "BLOCKS", "target_task_id": str(uuid4())},
        headers={"Authorization": "Bearer dummy"},
    )
    assert response.status_code == 201


def test_create_relation_self_link_returns_400(
    client: TestClient, task_service_mock: AsyncMock
) -> None:
    task_service_mock.create_relation.side_effect = TaskRelationSelfLinkError(
        "a task cannot be linked to itself"
    )
    response = client.post(
        f"/api/v1/tasks/{uuid4()}/relations",
        json={"relation_type": "RELATES_TO", "target_task_id": str(uuid4())},
        headers={"Authorization": "Bearer dummy"},
    )
    assert response.status_code == 400


def test_create_relation_duplicate_returns_409(
    client: TestClient, task_service_mock: AsyncMock
) -> None:
    task_service_mock.create_relation.side_effect = TaskRelationAlreadyExistsError(
        "this relation already exists between these tasks"
    )
    response = client.post(
        f"/api/v1/tasks/{uuid4()}/relations",
        json={"relation_type": "BLOCKS", "target_task_id": str(uuid4())},
        headers={"Authorization": "Bearer dummy"},
    )
    assert response.status_code == 409


def test_create_relation_target_unknown_returns_404(
    client: TestClient, task_service_mock: AsyncMock
) -> None:
    task_service_mock.create_relation.side_effect = TaskNotFoundError("task not found")
    response = client.post(
        f"/api/v1/tasks/{uuid4()}/relations",
        json={"relation_type": "BLOCKS", "target_task_id": str(uuid4())},
        headers={"Authorization": "Bearer dummy"},
    )
    assert response.status_code == 404


def test_delete_relation_returns_204(client: TestClient, task_service_mock: AsyncMock) -> None:
    response = client.delete(
        f"/api/v1/tasks/{uuid4()}/relations/{uuid4()}",
        headers={"Authorization": "Bearer dummy"},
    )
    assert response.status_code == 204
    task_service_mock.delete_relation.assert_awaited_once()


# ---------- get_by_id embeds relations (agent context) ----------


async def test_get_by_id_embeds_full_relations(
    service: TaskService,
    task_repo: AsyncMock,
    relations: AsyncMock,
) -> None:
    """When an agent fetches a task, the relations must be embedded in
    the response so the LLM sees the full linked-work context without
    a second round-trip."""
    p = make_principal()
    me = make_task(workspace_id=p.workspace_id, seq=1)
    blocker = make_task(workspace_id=p.workspace_id, seq=2)

    task_repo.get_by_id.return_value = me
    task_repo.list_by_ids.return_value = [blocker]
    relations.list_for_task.return_value = [
        TaskRelation(
            id=uuid4(),
            source_task_id=blocker.id,
            target_task_id=me.id,
            relation_type=TaskRelationType.BLOCKS,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    ]

    response = await service.get_by_id(me.id, p)

    assert response.public_id == "TASK-001"
    assert [item.task_id for item in response.relations.blocked_by] == [blocker.id]
    assert response.relations.blocks == []


async def test_get_by_id_returns_empty_relations_when_repo_missing() -> None:
    """Defensive: legacy DI without the relations repo still returns
    a usable detail response with empty buckets."""
    from app.domain.entities import Workspace

    task_repo = AsyncMock()
    workspace_repo = AsyncMock()
    seq_alloc = AsyncMock()

    p = make_principal()
    me = make_task(workspace_id=p.workspace_id, seq=1)
    task_repo.get_by_id.return_value = me
    workspace_repo.get_by_id.return_value = Workspace(
        id=p.workspace_id,
        name="Test",
        slug="test",
        task_prefix="TASK",
        next_task_seq=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    s = TaskService(
        tasks=task_repo,
        members=AsyncMock(),
        workspaces=workspace_repo,
        seq_allocator=seq_alloc,
        relations=None,
    )
    response = await s.get_by_id(me.id, p)
    assert response.relations.blocks == []
    assert response.relations.blocked_by == []
    assert response.relations.relates_to == []
