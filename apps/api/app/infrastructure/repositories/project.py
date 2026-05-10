from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import Project
from app.domain.enums import ProjectStatus
from app.infrastructure.db.models import ProjectModel


def _to_entity(row: ProjectModel) -> Project:
    return Project(
        id=row.id,
        workspace_id=row.workspace_id,
        name=row.name,
        description=row.description,
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlAlchemyProjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, project_id: UUID) -> Project | None:
        row = await self._session.get(ProjectModel, project_id)
        return _to_entity(row) if row is not None else None

    async def list_for_workspace(
        self,
        workspace_id: UUID,
        *,
        include_archived: bool = False,
        skip: int = 0,
        limit: int | None = None,
    ) -> tuple[list[Project], int]:
        base = select(ProjectModel).where(ProjectModel.workspace_id == workspace_id)
        if not include_archived:
            base = base.where(ProjectModel.status == ProjectStatus.ACTIVE)

        items_stmt = base.order_by(ProjectModel.name).offset(skip)
        if limit is not None:
            items_stmt = items_stmt.limit(limit)
        items_result = await self._session.execute(items_stmt)

        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()

        return [_to_entity(row) for row in items_result.scalars().all()], int(total)

    async def create(self, project: Project) -> Project:
        row = ProjectModel(
            id=project.id,
            workspace_id=project.workspace_id,
            name=project.name,
            description=project.description,
            status=project.status,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return _to_entity(row)

    async def update(
        self,
        project_id: UUID,
        *,
        name: str | None = None,
        description: str | None = None,
        status: ProjectStatus | None = None,
        clear_description: bool = False,
    ) -> Project:
        from app.domain.exceptions import ProjectNotFoundError

        row = await self._session.get(ProjectModel, project_id)
        if row is None:
            raise ProjectNotFoundError("project not found")
        if name is not None:
            row.name = name
        if clear_description:
            row.description = None
        elif description is not None:
            row.description = description
        if status is not None:
            row.status = status
        await self._session.flush()
        await self._session.refresh(row)
        return _to_entity(row)

    async def delete(self, project_id: UUID) -> None:
        from app.domain.exceptions import ProjectNotFoundError

        row = await self._session.get(ProjectModel, project_id)
        if row is None:
            raise ProjectNotFoundError("project not found")
        await self._session.delete(row)
        await self._session.flush()
