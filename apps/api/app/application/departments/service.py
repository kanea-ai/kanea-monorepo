from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError

from app.application.departments.ports import DepartmentRepository
from app.application.departments.schemas import (
    CreateDepartmentRequest,
    DepartmentResponse,
    UpdateDepartmentRequest,
)
from app.application.tasks.schemas import Principal
from app.domain.entities import Department
from app.domain.enums import MemberRole
from app.domain.exceptions import (
    DepartmentNameConflictError,
    DepartmentNotFoundError,
    ForbiddenError,
)


def _is_admin(principal: Principal) -> bool:
    return principal.role in (MemberRole.WORKSPACE_OWNER, MemberRole.WORKSPACE_ADMIN)


@dataclass(slots=True)
class DepartmentService:
    departments: DepartmentRepository

    async def list_for_workspace(
        self, principal: Principal, *, name: str | None = None
    ) -> list[DepartmentResponse]:
        """Anyone in the workspace can list departments — they're an
        organisational tag, not a permission boundary."""
        rows = await self.departments.list_for_workspace(principal.workspace_id, name=name)
        return [DepartmentResponse.from_entity(d) for d in rows]

    async def get_by_id(self, department_id: UUID, principal: Principal) -> DepartmentResponse:
        dept = await self._load_workspace_department(department_id, principal)
        return DepartmentResponse.from_entity(dept)

    async def create(
        self, request: CreateDepartmentRequest, principal: Principal
    ) -> DepartmentResponse:
        # Route-level RBAC is the primary guard; service-level is the
        # belt for direct callers.
        if not _is_admin(principal):
            raise ForbiddenError("workspace owner or admin role required")

        now = datetime.utcnow()
        try:
            dept = await self.departments.create(
                Department(
                    id=uuid4(),
                    workspace_id=principal.workspace_id,
                    name=request.name,
                    description=request.description,
                    created_at=now,
                    updated_at=now,
                )
            )
        except IntegrityError as exc:
            raise DepartmentNameConflictError(
                "a department with that name already exists in this workspace"
            ) from exc
        return DepartmentResponse.from_entity(dept)

    async def update(
        self,
        department_id: UUID,
        request: UpdateDepartmentRequest,
        principal: Principal,
    ) -> DepartmentResponse:
        if not _is_admin(principal):
            raise ForbiddenError("workspace owner or admin role required")

        await self._load_workspace_department(department_id, principal)

        clear_description = (
            "description" in request.model_fields_set and request.description is None
        )
        try:
            updated = await self.departments.update(
                department_id,
                name=request.name,
                description=request.description if not clear_description else None,
                clear_description=clear_description,
            )
        except IntegrityError as exc:
            raise DepartmentNameConflictError(
                "a department with that name already exists in this workspace"
            ) from exc
        return DepartmentResponse.from_entity(updated)

    async def delete(self, department_id: UUID, principal: Principal) -> None:
        """Hard delete. Teams pointing at this department have their
        ``department_id`` set to NULL via the FK SET NULL — they
        survive as un-filed teams rather than disappearing."""
        if not _is_admin(principal):
            raise ForbiddenError("workspace owner or admin role required")

        await self._load_workspace_department(department_id, principal)
        await self.departments.delete(department_id)

    async def _load_workspace_department(
        self, department_id: UUID, principal: Principal
    ) -> Department:
        dept = await self.departments.get_by_id(department_id)
        if dept is None or dept.workspace_id != principal.workspace_id:
            raise DepartmentNotFoundError("department not found")
        return dept
