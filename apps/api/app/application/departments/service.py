from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError

from app.application.audit.service import AuditLogService
from app.application.auth.ports import MemberRepository
from app.application.departments.ports import DepartmentRepository
from app.application.departments.schemas import (
    CreateDepartmentRequest,
    DepartmentResponse,
    UpdateDepartmentRequest,
)
from app.application.pagination import Page
from app.application.tasks.schemas import Principal
from app.domain.entities import Department, Member
from app.domain.enums import AuditAction, AuditResourceType, MemberRole
from app.domain.exceptions import (
    DepartmentHeadNotInWorkspaceError,
    DepartmentNameConflictError,
    DepartmentNotFoundError,
    ForbiddenError,
    MemberAlreadyDepartmentHeadError,
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
    # Members repo is required for head_id validation + resolving the
    # ``head`` summary embedded in DepartmentResponse. Optional so
    # tests that don't exercise head_id can pass ``departments=`` alone.
    members: MemberRepository | None = None

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
        head_map = await self._resolve_heads([d.head_id for d in rows])
        return Page[DepartmentResponse](
            items=[DepartmentResponse.from_entity(d, head=head_map.get(d.head_id)) for d in rows],
            total=total,
        )

    async def get_by_id(self, department_id: UUID, principal: Principal) -> DepartmentResponse:
        dept = await self._load_workspace_department(department_id, principal)
        head = await self._resolve_single_head(dept.head_id)
        return DepartmentResponse.from_entity(dept, head=head)

    async def create(
        self, request: CreateDepartmentRequest, principal: Principal
    ) -> DepartmentResponse:
        # Route-level RBAC is the primary guard; service-level is the
        # belt for direct callers.
        if not _is_admin(principal):
            raise ForbiddenError("workspace owner or admin role required")

        head: Member | None = None
        if request.head_id is not None:
            head = await self._validate_head(request.head_id, principal)
            await self._ensure_head_not_taken(request.head_id, excluding_department_id=None)

        now = datetime.utcnow()
        try:
            dept = await self.departments.create(
                Department(
                    id=uuid4(),
                    workspace_id=principal.workspace_id,
                    name=request.name,
                    description=request.description,
                    head_id=request.head_id,
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
                changes={
                    "name": dept.name,
                    "description": dept.description,
                    "head_id": str(dept.head_id) if dept.head_id else None,
                },
            )
        return DepartmentResponse.from_entity(dept, head=head)

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
        clear_head = "head_id" in request.model_fields_set and request.head_id is None

        head_member: Member | None = None
        if request.head_id is not None:
            head_member = await self._validate_head(request.head_id, principal)
            await self._ensure_head_not_taken(
                request.head_id, excluding_department_id=department_id
            )

        try:
            updated = await self.departments.update(
                department_id,
                name=request.name,
                description=request.description if not clear_description else None,
                clear_description=clear_description,
                head_id=request.head_id,
                clear_head=clear_head,
            )
        except IntegrityError as exc:
            raise DepartmentNameConflictError(
                "a department with that name already exists in this workspace"
            ) from exc
        # If the caller didn't touch head_id but the row still has one,
        # resolve it so the response carries the head summary too.
        if head_member is None and not clear_head and updated.head_id is not None:
            head_member = await self._resolve_single_head(updated.head_id)
        if self.audit_logs is not None:
            diff = _field_diff(
                {
                    "name": before.name,
                    "description": before.description,
                    "head_id": str(before.head_id) if before.head_id else None,
                },
                {
                    "name": updated.name,
                    "description": updated.description,
                    "head_id": str(updated.head_id) if updated.head_id else None,
                },
            )
            if diff:
                await self.audit_logs.record(
                    principal,
                    action=AuditAction.UPDATED,
                    resource_type=AuditResourceType.DEPARTMENT,
                    resource_id=updated.id,
                    changes=diff,
                )
        return DepartmentResponse.from_entity(updated, head=head_member)

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
                changes={
                    "name": before.name,
                    "description": before.description,
                    "head_id": str(before.head_id) if before.head_id else None,
                },
            )

    async def _load_workspace_department(
        self, department_id: UUID, principal: Principal
    ) -> Department:
        dept = await self.departments.get_by_id(department_id)
        if dept is None or dept.workspace_id != principal.workspace_id:
            raise DepartmentNotFoundError("department not found")
        return dept

    async def _ensure_head_not_taken(
        self, head_id: UUID, *, excluding_department_id: UUID | None
    ) -> None:
        """Enforce the one-department-per-head rule. Raises
        ``MemberAlreadyDepartmentHeadError`` (mapped to 409 at the
        route) when ``head_id`` already heads some OTHER department.
        ``excluding_department_id`` lets update re-save its own
        current head without tripping the check."""
        existing = await self.departments.get_for_head(head_id)
        if existing is not None and existing.id != excluding_department_id:
            raise MemberAlreadyDepartmentHeadError(
                f"this member already heads department '{existing.name}'; "
                "a member can only be the head of one department"
            )

    async def _validate_head(self, head_id: UUID, principal: Principal) -> Member:
        """Resolve head_id to a Member and ensure it belongs to the
        same workspace as the principal. Raises
        ``DepartmentHeadNotInWorkspaceError`` otherwise (mapped to 422
        at the route — it's a request-body validation failure)."""
        if self.members is None:  # pragma: no cover - DI invariant
            raise RuntimeError("DepartmentService.members is required for head_id validation")
        member = await self.members.get_by_id(head_id)
        if member is None or member.workspace_id != principal.workspace_id:
            raise DepartmentHeadNotInWorkspaceError(
                "head_id must reference a member of this workspace"
            )
        return member

    async def _resolve_heads(self, head_ids: list[UUID | None]) -> dict[UUID, Member]:
        """Batch-load the Member rows for a list of head_ids. Skips
        Nones; returns an empty dict if no members repo is wired."""
        if self.members is None:
            return {}
        non_null_ids = [hid for hid in head_ids if hid is not None]
        if not non_null_ids:
            return {}
        members = await self.members.list_by_ids(non_null_ids)
        return {m.id: m for m in members}

    async def _resolve_single_head(self, head_id: UUID | None) -> Member | None:
        if head_id is None or self.members is None:
            return None
        return await self.members.get_by_id(head_id)


def _field_diff(before: dict, after: dict) -> dict:
    """Build the {field: {from, to}} shape we use in audit-log
    ``changes`` payloads for UPDATED actions. Only fields that
    actually changed are included so the audit row stays compact."""
    diff: dict[str, dict] = {}
    for key in set(before) | set(after):
        if before.get(key) != after.get(key):
            diff[key] = {"from": before.get(key), "to": after.get(key)}
    return diff
