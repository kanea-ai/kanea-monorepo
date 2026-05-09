from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import TaskComment
from app.infrastructure.db.models import TaskCommentModel


def _to_entity(row: TaskCommentModel) -> TaskComment:
    return TaskComment(
        id=row.id,
        task_id=row.task_id,
        author_member_id=row.author_member_id,
        body=row.body,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlAlchemyTaskCommentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_task(self, task_id: UUID) -> list[TaskComment]:
        stmt = (
            select(TaskCommentModel)
            .where(TaskCommentModel.task_id == task_id)
            .order_by(TaskCommentModel.created_at, TaskCommentModel.id)
        )
        result = await self._session.execute(stmt)
        return [_to_entity(row) for row in result.scalars().all()]

    async def create(self, comment: TaskComment) -> TaskComment:
        row = TaskCommentModel(
            id=comment.id,
            task_id=comment.task_id,
            author_member_id=comment.author_member_id,
            body=comment.body,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return _to_entity(row)
