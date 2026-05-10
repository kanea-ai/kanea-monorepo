from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import Department
from app.infrastructure.db.models import DepartmentModel


def _to_entity(row: DepartmentModel) -> Department:
    return Department(
        id=row.id,
        workspace_id=row.workspace_id,
        name=row.name,
        description=row.description,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlAlchemyDepartmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, department_id: UUID) -> Department | None:
        row = await self._session.get(DepartmentModel, department_id)
        return _to_entity(row) if row is not None else None

    async def list_for_workspace(
        self,
        workspace_id: UUID,
        *,
        name: str | None = None,
    ) -> list[Department]:
        stmt = select(DepartmentModel).where(DepartmentModel.workspace_id == workspace_id)
        if name is not None and name != "":
            stmt = stmt.where(DepartmentModel.name.ilike(f"%{name}%"))
        stmt = stmt.order_by(DepartmentModel.name)
        result = await self._session.execute(stmt)
        return [_to_entity(row) for row in result.scalars().all()]

    async def create(self, department: Department) -> Department:
        row = DepartmentModel(
            id=department.id,
            workspace_id=department.workspace_id,
            name=department.name,
            description=department.description,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return _to_entity(row)

    async def update(
        self,
        department_id: UUID,
        *,
        name: str | None = None,
        description: str | None = None,
        clear_description: bool = False,
    ) -> Department:
        from app.domain.exceptions import DepartmentNotFoundError

        row = await self._session.get(DepartmentModel, department_id)
        if row is None:
            raise DepartmentNotFoundError("department not found")
        if name is not None:
            row.name = name
        if clear_description:
            row.description = None
        elif description is not None:
            row.description = description
        await self._session.flush()
        await self._session.refresh(row)
        return _to_entity(row)

    async def delete(self, department_id: UUID) -> None:
        from app.domain.exceptions import DepartmentNotFoundError

        row = await self._session.get(DepartmentModel, department_id)
        if row is None:
            raise DepartmentNotFoundError("department not found")
        await self._session.delete(row)
        await self._session.flush()
