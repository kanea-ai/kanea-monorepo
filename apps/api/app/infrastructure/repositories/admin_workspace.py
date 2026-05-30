from __future__ import annotations

# Cross-tenant workspace surface for the back-office. The listing
# joins ``members`` + ``tasks`` so a single round-trip populates the
# metrics column instead of N+1-ing per workspace. ``LEFT JOIN`` plus
# ``COALESCE`` keeps brand-new workspaces (no members yet, no tasks
# yet) from dropping out of the result.
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.admin.ports import WorkspaceRowWithMetrics
from app.domain.entities import Workspace
from app.domain.enums import MemberType
from app.infrastructure.db.models import MemberModel, TaskModel, WorkspaceModel


def _to_workspace(row: WorkspaceModel) -> Workspace:
    return Workspace(
        id=row.id,
        name=row.name,
        slug=row.slug,
        task_prefix=row.task_prefix,
        next_task_seq=row.next_task_seq,
        suspended_at=row.suspended_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlAlchemyAdminWorkspaceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_with_metrics(
        self,
        *,
        name: str | None = None,
        sort: str = "created_at_desc",
        skip: int = 0,
        limit: int = 25,
    ) -> tuple[list[WorkspaceRowWithMetrics], int]:
        # Per-workspace user count and task aggregates each live in
        # their own scalar subquery so the row count for the workspaces
        # table doesn't multiply with the joined fact tables. Postgres
        # plans these as correlated subqueries, which on our typical
        # workspace sizes (≤ tens of thousands of tasks) sits well
        # inside an index seek.
        users_subq = (
            select(func.count(MemberModel.id))
            .where(
                MemberModel.workspace_id == WorkspaceModel.id,
                MemberModel.type == MemberType.HUMAN,
            )
            .correlate(WorkspaceModel)
            .scalar_subquery()
            .label("total_users")
        )
        tasks_subq = (
            select(func.count(TaskModel.id))
            .where(TaskModel.workspace_id == WorkspaceModel.id)
            .correlate(WorkspaceModel)
            .scalar_subquery()
            .label("total_tasks")
        )
        tokens_subq = (
            select(func.coalesce(func.sum(TaskModel.tokens_used), 0))
            .where(TaskModel.workspace_id == WorkspaceModel.id)
            .correlate(WorkspaceModel)
            .scalar_subquery()
            .label("total_tokens_used")
        )

        base = select(
            WorkspaceModel,
            users_subq,
            tasks_subq,
            tokens_subq,
        )
        if name is not None and name != "":
            # Server-side substring match on either name or slug —
            # ``ilike`` is fine here, the back-office is a low-volume
            # surface.
            base = base.where(
                func.lower(WorkspaceModel.name).contains(name.lower())
                | func.lower(WorkspaceModel.slug).contains(name.lower())
            )

        ordering = {
            "created_at_desc": WorkspaceModel.created_at.desc(),
            "created_at_asc": WorkspaceModel.created_at.asc(),
            "name_asc": WorkspaceModel.name.asc(),
            "name_desc": WorkspaceModel.name.desc(),
            # Suspended rows first; nulls last so an active workspace
            # never floats above a suspended one when sorted by status.
            "suspended_at_desc": WorkspaceModel.suspended_at.desc().nullslast(),
        }
        base = base.order_by(ordering.get(sort, WorkspaceModel.created_at.desc()))

        items_stmt = base.offset(skip).limit(limit)
        items_result = await self._session.execute(items_stmt)
        items: list[WorkspaceRowWithMetrics] = []
        for row in items_result.all():
            ws_row: WorkspaceModel = row[0]
            items.append(
                WorkspaceRowWithMetrics(
                    workspace=_to_workspace(ws_row),
                    total_users=int(row[1] or 0),
                    total_tasks=int(row[2] or 0),
                    total_tokens_used=int(row[3] or 0),
                )
            )

        # Count: filter is the same as the page query, so we wrap it.
        count_stmt = select(func.count()).select_from(
            select(WorkspaceModel.id)
            .where(*(base.whereclause,) if base.whereclause is not None else ())
            .subquery()
        )
        total = (await self._session.execute(count_stmt)).scalar_one()

        return items, int(total)

    async def get_by_id(self, workspace_id: UUID) -> Workspace | None:
        row = await self._session.get(WorkspaceModel, workspace_id)
        return _to_workspace(row) if row is not None else None

    async def set_suspended_at(
        self, workspace_id: UUID, suspended_at: datetime | None
    ) -> Workspace:
        """Flip the soft-suspension column. Returns the refreshed row."""
        from app.domain.exceptions import WorkspaceNotFoundError

        stmt = (
            update(WorkspaceModel)
            .where(WorkspaceModel.id == workspace_id)
            .values(suspended_at=suspended_at)
            .returning(WorkspaceModel)
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            raise WorkspaceNotFoundError("workspace not found")
        await self._session.flush()
        return _to_workspace(row)

    async def get_metrics(self, workspace_id: UUID) -> tuple[int, int, int]:
        """Single-workspace metrics — three correlated COUNTs/SUM in
        one round-trip, same shape as the listing query."""
        stmt = select(
            (
                select(func.count(MemberModel.id))
                .where(
                    MemberModel.workspace_id == workspace_id,
                    MemberModel.type == MemberType.HUMAN,
                )
                .scalar_subquery()
            ).label("total_users"),
            (
                select(func.count(TaskModel.id))
                .where(TaskModel.workspace_id == workspace_id)
                .scalar_subquery()
            ).label("total_tasks"),
            (
                select(func.coalesce(func.sum(TaskModel.tokens_used), 0))
                .where(TaskModel.workspace_id == workspace_id)
                .scalar_subquery()
            ).label("total_tokens_used"),
        )
        row = (await self._session.execute(stmt)).one()
        return int(row[0] or 0), int(row[1] or 0), int(row[2] or 0)
