from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import Notification
from app.infrastructure.db.models import NotificationModel


def _to_entity(row: NotificationModel) -> Notification:
    return Notification(
        id=row.id,
        user_id=row.user_id,
        type=row.type,
        source_task_id=row.source_task_id,
        source_comment_id=row.source_comment_id,
        source_member_id=row.source_member_id,
        preview=row.preview,
        read_at=row.read_at,
        created_at=row.created_at,
    )


class SqlAlchemyNotificationRepository:
    """Thin CRUD over the notifications table. The "list inbox" path
    is the hot one — backed by ix_notifications_user_created which
    keeps `(user_id, created_at DESC)` cheap."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, notification: Notification) -> Notification:
        row = NotificationModel(
            id=notification.id,
            user_id=notification.user_id,
            type=notification.type,
            source_task_id=notification.source_task_id,
            source_comment_id=notification.source_comment_id,
            source_member_id=notification.source_member_id,
            preview=notification.preview,
            read_at=notification.read_at,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return _to_entity(row)

    async def list_for_user(
        self,
        user_id: UUID,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Notification]:
        stmt = (
            select(NotificationModel)
            .where(NotificationModel.user_id == user_id)
            .order_by(NotificationModel.created_at.desc(), NotificationModel.id.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return [_to_entity(r) for r in result.scalars().all()]

    async def unread_count(self, user_id: UUID) -> int:
        stmt = select(func.count(NotificationModel.id)).where(
            NotificationModel.user_id == user_id,
            NotificationModel.read_at.is_(None),
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def mark_read(self, notification_id: UUID, user_id: UUID) -> int:
        """Marks a single notification read iff it belongs to the user.
        Returns the rowcount so the caller can 404 on misses without an
        extra round-trip."""
        stmt = (
            update(NotificationModel)
            .where(
                NotificationModel.id == notification_id,
                NotificationModel.user_id == user_id,
                NotificationModel.read_at.is_(None),
            )
            .values(read_at=datetime.now(UTC))
            .execution_options(synchronize_session=False)
        )
        result = await self._session.execute(stmt)
        return int(result.rowcount or 0)

    async def mark_all_read(self, user_id: UUID) -> int:
        """Bulk-mark every unread notification for the user. Returns the
        number flipped from unread → read."""
        stmt = (
            update(NotificationModel)
            .where(
                NotificationModel.user_id == user_id,
                NotificationModel.read_at.is_(None),
            )
            .values(read_at=datetime.now(UTC))
            .execution_options(synchronize_session=False)
        )
        result = await self._session.execute(stmt)
        return int(result.rowcount or 0)
