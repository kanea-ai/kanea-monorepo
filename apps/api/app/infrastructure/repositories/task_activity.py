from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import TaskActivity
from app.domain.enums import TaskActivityType
from app.infrastructure.db.models import TaskActivityModel, TaskModel


def _to_entity(row: TaskActivityModel) -> TaskActivity:
    return TaskActivity(
        id=row.id,
        task_id=row.task_id,
        actor_member_id=row.actor_member_id,
        event_type=TaskActivityType(row.event_type),
        payload=dict(row.payload or {}),
        created_at=row.created_at,
    )


class SqlAlchemyTaskActivityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_task(self, task_id: UUID) -> list[TaskActivity]:
        stmt = (
            select(TaskActivityModel)
            .where(TaskActivityModel.task_id == task_id)
            .order_by(TaskActivityModel.created_at, TaskActivityModel.id)
        )
        result = await self._session.execute(stmt)
        return [_to_entity(row) for row in result.scalars().all()]

    async def list_for_project(self, project_id: UUID) -> list[TaskActivity]:
        """All activities across the project's tasks. Joined through
        tasks so we never leak rows from another project."""
        stmt = (
            select(TaskActivityModel)
            .join(TaskModel, TaskModel.id == TaskActivityModel.task_id)
            .where(TaskModel.project_id == project_id)
            .order_by(TaskActivityModel.created_at, TaskActivityModel.id)
        )
        result = await self._session.execute(stmt)
        return [_to_entity(row) for row in result.scalars().all()]

    async def create(self, activity: TaskActivity) -> TaskActivity:
        row = TaskActivityModel(
            id=activity.id,
            task_id=activity.task_id,
            actor_member_id=activity.actor_member_id,
            event_type=activity.event_type.value,
            payload=activity.payload,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return _to_entity(row)
