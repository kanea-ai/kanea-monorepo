from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import Workspace
from app.infrastructure.db.models import WorkspaceModel


def _to_entity(row: WorkspaceModel) -> Workspace:
    return Workspace(
        id=row.id,
        name=row.name,
        slug=row.slug,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlAlchemyWorkspaceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, workspace_id):  # type: ignore[no-untyped-def]
        row = await self._session.get(WorkspaceModel, workspace_id)
        return _to_entity(row) if row is not None else None

    async def create(self, workspace: Workspace) -> Workspace:
        row = WorkspaceModel(
            id=workspace.id,
            name=workspace.name,
            slug=workspace.slug,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return _to_entity(row)
