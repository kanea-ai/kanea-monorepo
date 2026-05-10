from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import Team
from app.infrastructure.db.models import TeamModel


def _to_entity(row: TeamModel) -> Team:
    return Team(
        id=row.id,
        workspace_id=row.workspace_id,
        name=row.name,
        description=row.description,
        department_id=row.department_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlAlchemyTeamRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, team_id: UUID) -> Team | None:
        row = await self._session.get(TeamModel, team_id)
        return _to_entity(row) if row is not None else None

    async def list_for_workspace(
        self,
        workspace_id: UUID,
        *,
        department_id: UUID | None = None,
        skip: int = 0,
        limit: int | None = None,
    ) -> tuple[list[Team], int]:
        # Build the base statement once and reuse it for both the
        # COUNT and the LIMIT/OFFSET query so the WHERE clauses are
        # guaranteed to match.
        base = select(TeamModel).where(TeamModel.workspace_id == workspace_id)
        if department_id is not None:
            base = base.where(TeamModel.department_id == department_id)

        items_stmt = base.order_by(TeamModel.name).offset(skip)
        if limit is not None:
            items_stmt = items_stmt.limit(limit)
        items_result = await self._session.execute(items_stmt)

        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()

        return [_to_entity(row) for row in items_result.scalars().all()], int(total)

    async def create(self, team: Team) -> Team:
        row = TeamModel(
            id=team.id,
            workspace_id=team.workspace_id,
            name=team.name,
            description=team.description,
            department_id=team.department_id,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return _to_entity(row)

    async def update(
        self,
        team_id: UUID,
        *,
        name: str | None = None,
        description: str | None = None,
        department_id: UUID | None = None,
        clear_description: bool = False,
        clear_department: bool = False,
    ) -> Team:
        from app.domain.exceptions import TeamNotFoundError

        row = await self._session.get(TeamModel, team_id)
        if row is None:
            raise TeamNotFoundError("team not found")
        if name is not None:
            row.name = name
        if clear_description:
            row.description = None
        elif description is not None:
            row.description = description
        if clear_department:
            row.department_id = None
        elif department_id is not None:
            row.department_id = department_id
        await self._session.flush()
        await self._session.refresh(row)
        return _to_entity(row)

    async def delete(self, team_id: UUID) -> None:
        from app.domain.exceptions import TeamNotFoundError

        row = await self._session.get(TeamModel, team_id)
        if row is None:
            raise TeamNotFoundError("team not found")
        await self._session.delete(row)
        await self._session.flush()
