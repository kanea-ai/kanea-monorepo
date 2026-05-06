from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from app.domain.entities import Task
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
    ) -> Task: ...
