from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from app.domain.entities import AgentStats, Invite, Member, Workspace
from app.domain.enums import MemberRole, TeamRole


@runtime_checkable
class InviteRepository(Protocol):
    async def create(self, invite: Invite) -> Invite: ...
    async def get_by_token_hash(self, token_hash: str) -> Invite | None: ...
    async def mark_accepted(self, invite_id: UUID) -> Invite: ...


@runtime_checkable
class TenantMemberRepository(Protocol):
    """Read/list operations for the team-management endpoints. Distinct
    from the auth-side MemberRepository (which only does single lookups
    + create) so each application module stays cohesive."""

    async def list_for_workspace(
        self,
        workspace_id: UUID,
        *,
        name: str | None = None,
        member_id: UUID | None = None,
        role: MemberRole | None = None,
        team_id: UUID | None = None,
        project_id: UUID | None = None,
        humans_only: bool = False,
        # Applied AFTER the filters above. Used by the service to
        # restrict non-admins to their team's members + themselves.
        visibility_team_id: UUID | None = None,
        visibility_self_id: UUID | None = None,
    ) -> list[Member]: ...
    async def get_by_id(self, member_id: UUID) -> Member | None: ...
    async def update_profile(
        self,
        member_id: UUID,
        *,
        name: str | None = None,
        role: MemberRole | None = None,
        priority: int | None = None,
    ) -> Member: ...
    async def set_team(
        self,
        member_id: UUID,
        *,
        team_id: UUID | None,
        team_role: TeamRole | None,
    ) -> Member: ...

    # Phase 5 batch 2 follow-up: per-member stats panel in the directory
    # detail dialog. Same SQL that backs /me/stats and the agent detail
    # page; it works for any member id.
    async def compute_agent_stats(self, member_id: UUID) -> AgentStats: ...


@runtime_checkable
class WorkspaceReadRepository(Protocol):
    async def get_by_id(self, workspace_id: UUID) -> Workspace | None: ...
