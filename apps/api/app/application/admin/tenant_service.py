from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from app.application.admin.ports import AdminWorkspaceRepository
from app.application.admin.tenant_ports import AdminTenantRepository
from app.application.admin.tenant_schemas import (
    AdminWorkspaceDetail,
    AdminWorkspaceUserRow,
    PatchWorkspaceUserRequest,
    WorkspaceStatusBreakdown,
)
from app.application.departments.schemas import UpdateDepartmentRequest
from app.application.departments.service import DepartmentService
from app.application.pagination import Page
from app.application.tasks.schemas import Principal
from app.application.tenants.schemas import SetMemberTeamRequest
from app.application.tenants.service import InviteService
from app.domain.enums import MemberRole, MemberType
from app.domain.exceptions import (
    DomainError,
    InvalidMemberTypeError,
    WorkspaceNotFoundError,
)

logger = logging.getLogger("kanea.admin.tenant")


class WorkspaceUserDualScopeError(DomainError):
    """Raised when a superadmin PATCH sets both ``team_id`` (non-null)
    AND ``department_id`` (non-null). A user cannot be a Department
    Head and on a Team simultaneously — the Round-2 isolation rule.
    Mapped to 400 at the route."""


@dataclass(slots=True)
class AdminTenantService:
    """Orchestrates the cross-tenant intervention endpoints. Reads
    flow through ``AdminTenantRepository``; writes route through the
    existing ``DepartmentService`` and ``InviteService`` so every
    constraint from Round-2 (head clears team, one MANAGER per team,
    head-blocks-assignment) carries over unchanged."""

    tenant: AdminTenantRepository
    workspaces: AdminWorkspaceRepository
    departments: DepartmentService
    invites: InviteService

    async def get_workspace_detail(self, workspace_id: UUID) -> AdminWorkspaceDetail:
        ws = await self.workspaces.get_by_id(workspace_id)
        if ws is None:
            raise WorkspaceNotFoundError("workspace not found")
        detail = await self.tenant.get_workspace_detail(workspace_id)
        return AdminWorkspaceDetail(
            id=ws.id,
            name=ws.name,
            slug=ws.slug,
            task_prefix=ws.task_prefix,
            suspended_at=ws.suspended_at,
            created_at=ws.created_at,
            updated_at=ws.updated_at,
            total_users=detail.total_users,
            total_tasks=detail.total_tasks,
            total_tokens_used=detail.total_tokens_used,
            total_teams=detail.total_teams,
            total_departments=detail.total_departments,
            total_projects=detail.total_projects,
            status_breakdown=WorkspaceStatusBreakdown(
                pending=detail.status_counts.pending,
                in_progress=detail.status_counts.in_progress,
                in_review=detail.status_counts.in_review,
                done=detail.status_counts.done,
                cancelled=detail.status_counts.cancelled,
                blocked=detail.status_counts.blocked,
            ),
        )

    async def list_workspace_users(
        self,
        workspace_id: UUID,
        *,
        name: str | None = None,
        skip: int = 0,
        limit: int = 25,
    ) -> Page[AdminWorkspaceUserRow]:
        ws = await self.workspaces.get_by_id(workspace_id)
        if ws is None:
            raise WorkspaceNotFoundError("workspace not found")
        rows, total = await self.tenant.list_workspace_users(
            workspace_id, name=name, skip=skip, limit=limit
        )
        return Page[AdminWorkspaceUserRow](items=[_to_row(r) for r in rows], total=total)

    async def patch_workspace_user(
        self,
        workspace_id: UUID,
        target_user_id: UUID,
        request: PatchWorkspaceUserRequest,
        *,
        superadmin_user_id: UUID,
    ) -> AdminWorkspaceUserRow:
        """Apply department / team changes on behalf of the tenant.

        Order of operations matters: department promotion clears
        team (Round-2 rule), so we run dept changes BEFORE team
        changes. If both ``team_id`` (non-null) and ``department_id``
        (non-null) are present we refuse before touching anything —
        the rule is they can't co-exist."""
        has_team = "team_id" in request.model_fields_set
        has_team_role = "team_role" in request.model_fields_set
        has_department = "department_id" in request.model_fields_set
        if (
            has_team
            and request.team_id is not None
            and has_department
            and request.department_id is not None
        ):
            raise WorkspaceUserDualScopeError(
                "a user cannot simultaneously be a Department Head and on a Team"
            )

        ws = await self.workspaces.get_by_id(workspace_id)
        if ws is None:
            raise WorkspaceNotFoundError("workspace not found")

        member_row = await self.tenant.find_member_by_user(workspace_id, target_user_id)
        if member_row is None:
            raise InvalidMemberTypeError("user is not a member of this workspace")

        # Synthesize a workspace-scoped Principal so we can reuse the
        # existing DepartmentService / InviteService logic with all
        # of Round-2's constraints intact. We attribute audit-log
        # actions to the first OWNER in the workspace (real, present
        # member id) since the back-office actor isn't a workspace
        # member at all.
        actor_member_id = await self.tenant.find_first_owner_member_id(workspace_id)
        principal = Principal(
            member_id=actor_member_id or member_row.member_id,
            workspace_id=workspace_id,
            type=MemberType.HUMAN,
            priority=1,
            scope="human",
            role=MemberRole.WORKSPACE_OWNER,
        )

        # 1. Department changes — promotion clears the user's team
        #    inside DepartmentService.update; demotion just clears
        #    the FK on the previously-headed department.
        if has_department:
            if request.department_id is not None:
                # Promote: set departments.head_id = this member's id.
                await self.departments.update(
                    request.department_id,
                    UpdateDepartmentRequest(head_id=member_row.member_id),
                    principal,
                )
                logger.info(
                    "admin.tenant.head_promoted",
                    extra={
                        "workspace_id": str(workspace_id),
                        "user_id": str(target_user_id),
                        "department_id": str(request.department_id),
                        "by_superadmin": str(superadmin_user_id),
                    },
                )
            else:
                # Demote: clear head_id on the department they head.
                if member_row.headed_department_id is not None:
                    await self.departments.update(
                        member_row.headed_department_id,
                        UpdateDepartmentRequest.model_validate({"head_id": None}),
                        principal,
                    )
                    logger.info(
                        "admin.tenant.head_demoted",
                        extra={
                            "workspace_id": str(workspace_id),
                            "user_id": str(target_user_id),
                            "department_id": str(member_row.headed_department_id),
                            "by_superadmin": str(superadmin_user_id),
                        },
                    )

        # 2. Team changes. Reuses InviteService.set_member_team's
        #    full constraint set: refuses for current heads, and
        #    auto-demotes a sitting MANAGER/LEAD.
        #
        # Spec carve-out: when the superadmin assigns a Team to a
        # member who is currently a Department Head, we silently
        # demote them from headship first (clear that dept's
        # head_id) so the team assignment can land. The Round-2
        # service-level refusal still fires for *any other* caller —
        # this auto-clear is gated to the back-office orchestrator
        # only.
        if has_team or has_team_role:
            if request.team_id is not None and member_row.headed_department_id is not None:
                await self.departments.update(
                    member_row.headed_department_id,
                    UpdateDepartmentRequest.model_validate({"head_id": None}),
                    principal,
                )
                logger.info(
                    "admin.tenant.head_demoted_for_team_assignment",
                    extra={
                        "workspace_id": str(workspace_id),
                        "user_id": str(target_user_id),
                        "department_id": str(member_row.headed_department_id),
                        "by_superadmin": str(superadmin_user_id),
                    },
                )
            await self.invites.set_member_team(
                member_row.member_id,
                SetMemberTeamRequest(team_id=request.team_id, team_role=request.team_role),
                principal,
            )
            logger.info(
                "admin.tenant.team_assigned",
                extra={
                    "workspace_id": str(workspace_id),
                    "user_id": str(target_user_id),
                    "team_id": (str(request.team_id) if request.team_id else None),
                    "team_role": (request.team_role.value if request.team_role else None),
                    "by_superadmin": str(superadmin_user_id),
                },
            )

        # Re-read the joined row so the response reflects the merged
        # state after dept + team mutations.
        refreshed = await self.tenant.find_member_by_user(workspace_id, target_user_id)
        if refreshed is None:  # pragma: no cover - reads after mutations
            raise InvalidMemberTypeError("user is not a member of this workspace")
        return _to_row(refreshed)


def _to_row(r) -> AdminWorkspaceUserRow:
    return AdminWorkspaceUserRow(
        member_id=r.member_id,
        user_id=r.user_id,
        email=r.email,
        full_name=r.full_name,
        type=r.type,
        role=r.role,
        is_suspended=r.is_suspended,
        team_id=r.team_id,
        team_name=r.team_name,
        team_role=r.team_role,
        team_department_id=r.team_department_id,
        team_department_name=r.team_department_name,
        headed_department_id=r.headed_department_id,
        headed_department_name=r.headed_department_name,
    )
