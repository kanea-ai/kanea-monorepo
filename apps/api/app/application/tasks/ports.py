from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from app.domain.entities import Task, TaskActivity, TaskComment, TaskRating, TaskRelation
from app.domain.enums import TaskRelationType, TaskStatus


@runtime_checkable
class TaskRepository(Protocol):
    async def get_by_id(self, task_id: UUID) -> Task | None: ...
    async def assign(self, task_id: UUID, assignee_id: UUID) -> Task: ...
    async def list_by_workspace(
        self,
        workspace_id: UUID,
        *,
        status: TaskStatus | None = None,
        blocked_only: bool = False,
        project_id: UUID | None = None,
        team_id: UUID | None = None,
        assignee_id: UUID | None = None,
    ) -> list[Task]: ...
    async def update_status(
        self,
        task_id: UUID,
        *,
        status: TaskStatus,
        tokens_used: int | None = None,
    ) -> Task: ...
    async def set_blocked(
        self,
        task_id: UUID,
        *,
        is_blocked: bool,
        blocked_reason: str | None,
    ) -> Task: ...
    async def create(self, task: Task) -> Task: ...
    async def list_by_ids(self, task_ids: list[UUID]) -> list[Task]: ...
    async def update_links(
        self,
        task_id: UUID,
        *,
        project_id: UUID | None,
        team_id: UUID | None,
        clear_project: bool = False,
        clear_team: bool = False,
    ) -> Task: ...


@runtime_checkable
class WorkspaceTaskSeqRepository(Protocol):
    """Atomic per-workspace seq allocator used to mint task public ids
    like ``DEVOPS-001``. Returns (seq, prefix) — the seq is reserved for
    the caller's transaction even under concurrent inserts."""

    async def allocate_next_task_seq(self, workspace_id: UUID) -> tuple[int, str]: ...


@runtime_checkable
class TaskRatingRepository(Protocol):
    async def get_for_task(self, task_id: UUID) -> TaskRating | None: ...
    async def create(self, rating: TaskRating) -> TaskRating: ...


@runtime_checkable
class TaskCommentRepository(Protocol):
    async def list_for_task(self, task_id: UUID) -> list[TaskComment]: ...
    async def create(self, comment: TaskComment) -> TaskComment: ...


@runtime_checkable
class TaskActivityRepository(Protocol):
    async def list_for_task(self, task_id: UUID) -> list[TaskActivity]: ...
    async def list_for_project(self, project_id: UUID) -> list[TaskActivity]: ...
    async def create(self, activity: TaskActivity) -> TaskActivity: ...


@runtime_checkable
class TaskRelationRepository(Protocol):
    async def get_existing(
        self,
        *,
        source_task_id: UUID,
        target_task_id: UUID,
        relation_type: TaskRelationType,
    ) -> TaskRelation | None: ...
    async def list_for_task(self, task_id: UUID) -> list[TaskRelation]: ...
    async def get_by_id(self, relation_id: UUID) -> TaskRelation | None: ...
    async def create(self, relation: TaskRelation) -> TaskRelation: ...
    async def delete(self, relation_id: UUID) -> bool: ...
