from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from app.domain.entities import Task


@runtime_checkable
class TaskRepository(Protocol):
    async def get_by_id(self, task_id: UUID) -> Task | None: ...
    async def assign(self, task_id: UUID, assignee_id: UUID) -> Task: ...
