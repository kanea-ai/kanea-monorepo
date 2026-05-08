from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import TaskRating
from app.infrastructure.db.models import TaskRatingModel


def _to_entity(row: TaskRatingModel) -> TaskRating:
    return TaskRating(
        id=row.id,
        task_id=row.task_id,
        rated_by_id=row.rated_by_id,
        rated_member_id=row.rated_member_id,
        score=row.score,
        feedback=row.feedback,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlAlchemyTaskRatingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_for_task(self, task_id: UUID) -> TaskRating | None:
        stmt = select(TaskRatingModel).where(TaskRatingModel.task_id == task_id)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _to_entity(row) if row is not None else None

    async def create(self, rating: TaskRating) -> TaskRating:
        row = TaskRatingModel(
            id=rating.id,
            task_id=rating.task_id,
            rated_by_id=rating.rated_by_id,
            rated_member_id=rating.rated_member_id,
            score=rating.score,
            feedback=rating.feedback,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return _to_entity(row)
