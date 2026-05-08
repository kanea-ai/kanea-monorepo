from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from app.domain.entities import Task, TaskRating
from app.domain.enums import TaskStatus


@runtime_checkable
class TaskRepository(Protocol):
    async def get_by_id(self, task_id: UUID) -> Task | None: ...
    async def assign(self, task_id: UUID, assignee_id: UUID) -> Task: ...
    async def list_by_workspace(
        self,
        workspace_id: UUID,
        *,
        status: TaskStatus | None = None,
    ) -> list[Task]: ...
    async def update_status(
        self,
        task_id: UUID,
        *,
        status: TaskStatus,
        blocked_reason: str | None,
        tokens_used: int | None = None,
    ) -> Task: ...
    async def create(self, task: Task) -> Task: ...


@runtime_checkable
class TaskRatingRepository(Protocol):
    async def get_for_task(self, task_id: UUID) -> TaskRating | None: ...
    async def create(self, rating: TaskRating) -> TaskRating: ...
