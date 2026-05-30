from __future__ import annotations

# Cross-tenant platform counters. Two SQL calls, by design:
#
# 1. ``get_summary`` — three counters returned in a single SELECT via
#    scalar subqueries:
#      - active workspaces (workspaces.suspended_at IS NULL)
#      - registered users
#      - sum of all task tokens used
#    Postgres plans these against indexed columns; on a workspace-
#    sized dataset (low thousands of users, tens of thousands of
#    tasks) it's a one-stat-sample query.
#
# 2. ``list_recent_signups`` — ``users WHERE created_at >= now() - N``
#    ordered by created_at desc, capped at ``limit``. ``users.created_at``
#    isn't indexed today; on the dashboard's small-N read this still
#    plans as a sequential scan well under 10 ms at our size. If the
#    dashboard grows hot we can add an index in a follow-up.
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.admin.metrics_ports import (
    AdminMetricsRepository,
    PlatformSummaryAggregates,
)
from app.domain.entities import User
from app.infrastructure.db.models import TaskModel, UserModel, WorkspaceModel


def _to_user(row: UserModel) -> User:
    return User(
        id=row.id,
        email=row.email,
        full_name=row.full_name,
        password_hash=row.password_hash,
        oauth_provider=row.oauth_provider,
        oauth_id=row.oauth_id,
        is_superadmin=row.is_superadmin,
        is_banned=row.is_banned,
        sessions_invalidated_at=row.sessions_invalidated_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlAlchemyAdminMetricsRepository(AdminMetricsRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_summary(self) -> PlatformSummaryAggregates:
        active_workspaces = (
            select(func.count(WorkspaceModel.id))
            .where(WorkspaceModel.suspended_at.is_(None))
            .scalar_subquery()
        )
        registered_users = select(func.count(UserModel.id)).scalar_subquery()
        total_tokens = select(func.coalesce(func.sum(TaskModel.tokens_used), 0)).scalar_subquery()
        stmt = select(
            active_workspaces.label("active_workspaces"),
            registered_users.label("registered_users"),
            total_tokens.label("total_tokens_used"),
        )
        row = (await self._session.execute(stmt)).one()
        return PlatformSummaryAggregates(
            total_active_workspaces=int(row[0] or 0),
            total_registered_users=int(row[1] or 0),
            total_tokens_used=int(row[2] or 0),
        )

    async def list_recent_signups(self, *, since_days: int = 7, limit: int = 50) -> list[User]:
        cutoff = datetime.now(UTC) - timedelta(days=since_days)
        stmt = (
            select(UserModel)
            .where(UserModel.created_at >= cutoff)
            .order_by(desc(UserModel.created_at))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [_to_user(row) for row in result.scalars().all()]
