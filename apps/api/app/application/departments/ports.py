from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from app.domain.entities import Department


@runtime_checkable
class DepartmentRepository(Protocol):
    async def get_by_id(self, department_id: UUID) -> Department | None: ...
    async def list_for_workspace(
        self,
        workspace_id: UUID,
        *,
        name: str | None = None,
        skip: int = 0,
        limit: int | None = None,
    ) -> tuple[list[Department], int]: ...
    async def create(self, department: Department) -> Department: ...
    async def get_for_head(self, head_member_id: UUID) -> Department | None:
        """Reverse lookup: the (at most one) Department whose
        ``head_id`` equals the given member. ``None`` if no
        department is headed by this member. Used by the service
        layer to enforce the one-department-per-head rule before
        attempting the write."""
        ...

    async def update(
        self,
        department_id: UUID,
        *,
        name: str | None = None,
        description: str | None = None,
        clear_description: bool = False,
        head_id: UUID | None = None,
        clear_head: bool = False,
    ) -> Department: ...
    async def delete(self, department_id: UUID) -> None: ...
