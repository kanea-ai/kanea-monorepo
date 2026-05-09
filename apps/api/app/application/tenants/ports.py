from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from app.domain.entities import Invite, Member, Workspace
from app.domain.enums import TeamRole


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

    async def list_for_workspace(self, workspace_id: UUID) -> list[Member]: ...
    async def get_by_id(self, member_id: UUID) -> Member | None: ...
    async def set_team(
        self,
        member_id: UUID,
        *,
        team_id: UUID | None,
        team_role: TeamRole | None,
    ) -> Member: ...


@runtime_checkable
class WorkspaceReadRepository(Protocol):
    async def get_by_id(self, workspace_id: UUID) -> Workspace | None: ...
