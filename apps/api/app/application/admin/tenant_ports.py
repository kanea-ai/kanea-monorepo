from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from uuid import UUID

from app.domain.enums import MemberRole, MemberType, TeamRole


@dataclass(slots=True)
class WorkspaceStatusCounts:
    pending: int
    in_progress: int
    in_review: int
    done: int
    cancelled: int
    blocked: int


@dataclass(slots=True)
class WorkspaceDetailRow:
    total_users: int
    total_tasks: int
    total_tokens_used: int
    total_teams: int
    total_departments: int
    total_projects: int
    status_counts: WorkspaceStatusCounts


@dataclass(slots=True)
class WorkspaceUserDetailRow:
    member_id: UUID
    user_id: UUID
    email: str | None
    full_name: str
    type: MemberType
    role: MemberRole
    is_suspended: bool
    team_id: UUID | None
    team_name: str | None
    team_role: TeamRole | None
    team_department_id: UUID | None
    team_department_name: str | None
    headed_department_id: UUID | None
    headed_department_name: str | None


@runtime_checkable
class AdminTenantRepository(Protocol):
    """Cross-tenant intervention surface. Read-side joins workspaces
    against members/tasks/teams/departments so the detail / users
    pages each come back in a single round-trip."""

    async def get_workspace_detail(self, workspace_id: UUID) -> WorkspaceDetailRow: ...

    async def list_workspace_users(
        self,
        workspace_id: UUID,
        *,
        name: str | None = None,
        skip: int = 0,
        limit: int = 25,
    ) -> tuple[list[WorkspaceUserDetailRow], int]: ...

    async def find_member_by_user(
        self, workspace_id: UUID, user_id: UUID
    ) -> WorkspaceUserDetailRow | None:
        """Convenience read: locate the workspace's member row for a
        given global user id. Powers the PATCH path which is keyed by
        ``user_id`` from the URL but routed through the existing
        ``set_member_team`` (member-id based)."""
        ...

    async def find_first_owner_member_id(self, workspace_id: UUID) -> UUID | None:
        """Used to attribute audit-log entries when a superadmin
        intervenes in a tenant — we don't have a real workspace
        principal in the back-office flow, so we borrow the first
        OWNER's member id as the actor."""
        ...
