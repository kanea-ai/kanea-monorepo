from __future__ import annotations

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import TaskRelation
from app.domain.enums import TaskRelationType
from app.infrastructure.db.models import TaskRelationModel


def _to_entity(row: TaskRelationModel) -> TaskRelation:
    return TaskRelation(
        id=row.id,
        source_task_id=row.source_task_id,
        target_task_id=row.target_task_id,
        relation_type=row.relation_type,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlAlchemyTaskRelationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_existing(
        self,
        *,
        source_task_id: UUID,
        target_task_id: UUID,
        relation_type: TaskRelationType,
    ) -> TaskRelation | None:
        stmt = select(TaskRelationModel).where(
            TaskRelationModel.source_task_id == source_task_id,
            TaskRelationModel.target_task_id == target_task_id,
            TaskRelationModel.relation_type == relation_type,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _to_entity(row) if row is not None else None

    async def list_for_task(self, task_id: UUID) -> list[TaskRelation]:
        """All rows that touch this task — either as source or target.
        The service layer slices these into the seven UI buckets."""
        stmt = select(TaskRelationModel).where(
            or_(
                TaskRelationModel.source_task_id == task_id,
                TaskRelationModel.target_task_id == task_id,
            )
        )
        result = await self._session.execute(stmt)
        return [_to_entity(row) for row in result.scalars().all()]

    async def get_by_id(self, relation_id: UUID) -> TaskRelation | None:
        row = await self._session.get(TaskRelationModel, relation_id)
        return _to_entity(row) if row is not None else None

    async def create(self, relation: TaskRelation) -> TaskRelation:
        """Insert. Surfaces the unique-constraint violation as None to
        the service when the relation already exists, so the service
        can stay idempotent without a separate get-then-create dance."""
        row = TaskRelationModel(
            id=relation.id,
            source_task_id=relation.source_task_id,
            target_task_id=relation.target_task_id,
            relation_type=relation.relation_type,
        )
        self._session.add(row)
        try:
            await self._session.flush()
        except IntegrityError:
            await self._session.rollback()
            raise
        await self._session.refresh(row)
        return _to_entity(row)

    async def delete(self, relation_id: UUID) -> bool:
        row = await self._session.get(TaskRelationModel, relation_id)
        if row is None:
            return False
        await self._session.delete(row)
        await self._session.flush()
        return True
