from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError

from app.application.audit.service import AuditLogService
from app.application.departments.ports import DepartmentRepository
from app.application.departments.schemas import (
    CreateDepartmentRequest,
    DepartmentResponse,
    UpdateDepartmentRequest,
)
from app.application.pagination import Page
from app.application.tasks.schemas import Principal
from app.domain.entities import Department
from app.domain.enums import AuditAction, AuditResourceType, MemberRole
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
    # Optional so legacy unit-test constructors stay valid; mutations
    # skip the audit write when None — the route-level wiring always
    # provides one in production.
    audit_logs: AuditLogService | None = None

    async def list_for_workspace(
        self,
        principal: Principal,
        *,
        name: str | None = None,
        skip: int = 0,
        limit: int | None = None,
    ) -> Page[DepartmentResponse]:
        """Anyone in the workspace can list departments — they're an
        organisational tag, not a permission boundary."""
        rows, total = await self.departments.list_for_workspace(
            principal.workspace_id, name=name, skip=skip, limit=limit
        )
        return Page[DepartmentResponse](
            items=[DepartmentResponse.from_entity(d) for d in rows], total=total
        )

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
        if self.audit_logs is not None:
            await self.audit_logs.record(
                principal,
                action=AuditAction.CREATED,
                resource_type=AuditResourceType.DEPARTMENT,
                resource_id=dept.id,
                changes={"name": dept.name, "description": dept.description},
            )
        return DepartmentResponse.from_entity(dept)

    async def update(
        self,
        department_id: UUID,
        request: UpdateDepartmentRequest,
        principal: Principal,
    ) -> DepartmentResponse:
        if not _is_admin(principal):
            raise ForbiddenError("workspace owner or admin role required")

        before = await self._load_workspace_department(department_id, principal)

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
        if self.audit_logs is not None:
            diff = _field_diff(
                {"name": before.name, "description": before.description},
                {"name": updated.name, "description": updated.description},
            )
            if diff:
                await self.audit_logs.record(
                    principal,
                    action=AuditAction.UPDATED,
                    resource_type=AuditResourceType.DEPARTMENT,
                    resource_id=updated.id,
                    changes=diff,
                )
        return DepartmentResponse.from_entity(updated)

    async def delete(self, department_id: UUID, principal: Principal) -> None:
        """Hard delete. Teams pointing at this department have their
        ``department_id`` set to NULL via the FK SET NULL — they
        survive as un-filed teams rather than disappearing."""
        if not _is_admin(principal):
            raise ForbiddenError("workspace owner or admin role required")

        before = await self._load_workspace_department(department_id, principal)
        await self.departments.delete(department_id)
        if self.audit_logs is not None:
            await self.audit_logs.record(
                principal,
                action=AuditAction.DELETED,
                resource_type=AuditResourceType.DEPARTMENT,
                resource_id=before.id,
                changes={"name": before.name, "description": before.description},
            )

    async def _load_workspace_department(
        self, department_id: UUID, principal: Principal
    ) -> Department:
        dept = await self.departments.get_by_id(department_id)
        if dept is None or dept.workspace_id != principal.workspace_id:
            raise DepartmentNotFoundError("department not found")
        return dept


def _field_diff(before: dict, after: dict) -> dict:
    """Build the {field: {from, to}} shape we use in audit-log
    ``changes`` payloads for UPDATED actions. Only fields that
    actually changed are included so the audit row stays compact."""
    diff: dict[str, dict] = {}
    for key in set(before) | set(after):
        if before.get(key) != after.get(key):
            diff[key] = {"from": before.get(key), "to": after.get(key)}
    return diff
