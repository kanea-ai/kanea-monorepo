from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import Task
from app.domain.enums import TaskStatus
from app.domain.exceptions import TaskNotFoundError
from app.infrastructure.db.models import TaskModel


def _to_entity(row: TaskModel) -> Task:
    return Task(
        id=row.id,
        workspace_id=row.workspace_id,
        created_by_id=row.created_by_id,
        title=row.title,
        status=row.status,
        priority=row.priority,
        description=row.description,
        assignee_id=row.assignee_id,
        due_at=row.due_at,
        completed_at=row.completed_at,
        blocked_reason=row.blocked_reason,
        tokens_used=row.tokens_used,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlAlchemyTaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, task_id: UUID) -> Task | None:
        row = await self._session.get(TaskModel, task_id)
        return _to_entity(row) if row is not None else None

    async def assign(self, task_id: UUID, assignee_id: UUID) -> Task:
        row = await self._session.get(TaskModel, task_id)
        if row is None:
            raise TaskNotFoundError("task not found")
        row.assignee_id = assignee_id
        await self._session.flush()
        await self._session.refresh(row)
        return _to_entity(row)

    async def list_by_workspace(
        self,
        workspace_id: UUID,
        *,
        status: TaskStatus | None = None,
    ) -> list[Task]:
        stmt = select(TaskModel).where(TaskModel.workspace_id == workspace_id)
        if status is not None:
            stmt = stmt.where(TaskModel.status == status)
        stmt = stmt.order_by(TaskModel.priority, TaskModel.created_at)
        result = await self._session.execute(stmt)
        return [_to_entity(row) for row in result.scalars().all()]

    async def update_status(
        self,
        task_id: UUID,
        *,
        status: TaskStatus,
        blocked_reason: str | None,
        tokens_used: int | None = None,
    ) -> Task:
        row = await self._session.get(TaskModel, task_id)
        if row is None:
            raise TaskNotFoundError("task not found")
        row.status = status
        row.blocked_reason = blocked_reason
        if tokens_used is not None:
            # Cumulative — agents report the *total* spent so far, not a
            # delta. Keeps the contract idempotent under retries.
            row.tokens_used = tokens_used
        # Stamp completion when transitioning into DONE; clear it if the
        # task is reopened (DONE -> elsewhere isn't currently legal per
        # _ALLOWED_TRANSITIONS, but defensive).
        if status is TaskStatus.DONE:
            from datetime import UTC
            from datetime import datetime as _dt

            row.completed_at = _dt.now(UTC)
        else:
            row.completed_at = None
        await self._session.flush()
        await self._session.refresh(row)
        return _to_entity(row)

    async def create(self, task: Task) -> Task:
        row = TaskModel(
            id=task.id,
            workspace_id=task.workspace_id,
            created_by_id=task.created_by_id,
            title=task.title,
            status=task.status,
            priority=task.priority,
            description=task.description,
            assignee_id=task.assignee_id,
            due_at=task.due_at,
            blocked_reason=task.blocked_reason,
            tokens_used=task.tokens_used,
            completed_at=task.completed_at,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return _to_entity(row)
