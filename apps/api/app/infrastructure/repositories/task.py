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
        seq=row.seq,
        description=row.description,
        assignee_id=row.assignee_id,
        due_at=row.due_at,
        is_blocked=row.is_blocked,
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

    async def list_by_ids(self, task_ids: list[UUID]) -> list[Task]:
        """Bulk lookup used by the relations endpoint to materialise the
        counterpart tasks for the UI without N round-trips."""
        if not task_ids:
            return []
        stmt = select(TaskModel).where(TaskModel.id.in_(task_ids))
        result = await self._session.execute(stmt)
        return [_to_entity(row) for row in result.scalars().all()]

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
        blocked_only: bool = False,
    ) -> list[Task]:
        stmt = select(TaskModel).where(TaskModel.workspace_id == workspace_id)
        if status is not None:
            stmt = stmt.where(TaskModel.status == status)
        if blocked_only:
            stmt = stmt.where(TaskModel.is_blocked.is_(True))
        stmt = stmt.order_by(TaskModel.priority, TaskModel.created_at)
        result = await self._session.execute(stmt)
        return [_to_entity(row) for row in result.scalars().all()]

    async def update_status(
        self,
        task_id: UUID,
        *,
        status: TaskStatus,
        tokens_used: int | None = None,
    ) -> Task:
        row = await self._session.get(TaskModel, task_id)
        if row is None:
            raise TaskNotFoundError("task not found")
        row.status = status
        if tokens_used is not None:
            # Cumulative — agents report the *total* spent so far, not a
            # delta. Keeps the contract idempotent under retries.
            row.tokens_used = tokens_used
        # Stamp completion when transitioning into DONE; clear it if the
        # task is reopened.
        if status is TaskStatus.DONE:
            from datetime import UTC
            from datetime import datetime as _dt

            row.completed_at = _dt.now(UTC)
        else:
            row.completed_at = None
        await self._session.flush()
        await self._session.refresh(row)
        return _to_entity(row)

    async def set_blocked(
        self,
        task_id: UUID,
        *,
        is_blocked: bool,
        blocked_reason: str | None,
    ) -> Task:
        """Toggle the blocked flag without touching status. Reason is
        cleared when unblocking."""
        row = await self._session.get(TaskModel, task_id)
        if row is None:
            raise TaskNotFoundError("task not found")
        row.is_blocked = is_blocked
        row.blocked_reason = blocked_reason if is_blocked else None
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
            seq=task.seq,
            is_blocked=task.is_blocked,
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
