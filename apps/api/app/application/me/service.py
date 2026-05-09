from __future__ import annotations

from dataclasses import dataclass

from app.application.auth.ports import (
    PasswordHasher,
    UserRepository,
    WorkspaceRepository,
)
from app.application.me.ports import MeMemberRepository
from app.application.me.schemas import (
    ChangePasswordRequest,
    MeProfileResponse,
    MeStatsResponse,
    UpdateMeRequest,
)
from app.application.tasks.schemas import Principal
from app.domain.exceptions import AuthenticationError, InvalidMemberTypeError


@dataclass(slots=True)
class MeService:
    users: UserRepository
    members: MeMemberRepository
    workspaces: WorkspaceRepository
    hasher: PasswordHasher

    async def get_profile(self, principal: Principal) -> MeProfileResponse:
        member = await self.members.get_by_id(principal.member_id)
        if member is None or member.workspace_id != principal.workspace_id:
            # Token still valid but the member row vanished (workspace
            # left, deleted, etc.) — front-end should treat this as a
            # forced logout.
            raise InvalidMemberTypeError("member not found")
        if member.user_id is None:  # pragma: no cover - schema invariant
            raise InvalidMemberTypeError("member is not a human user")

        user = await self.users.get_by_id(member.user_id)
        if user is None:  # pragma: no cover - FK invariant
            raise InvalidMemberTypeError("user record missing")

        workspace = await self.workspaces.get_by_id(member.workspace_id)
        if workspace is None:  # pragma: no cover - FK invariant
            raise InvalidMemberTypeError("workspace missing")

        return MeProfileResponse(
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
            has_password=user.password_hash is not None,
            oauth_provider=user.oauth_provider,
            member_id=member.id,
            workspace_id=workspace.id,
            workspace_name=workspace.name,
            role=member.role,
            type=member.type,
            team_id=member.team_id,
            team_role=member.team_role,
        )

    async def update_profile(
        self, principal: Principal, request: UpdateMeRequest
    ) -> MeProfileResponse:
        member = await self.members.get_by_id(principal.member_id)
        if member is None or member.user_id is None:
            raise InvalidMemberTypeError("member not found")
        await self.users.update_full_name(member.user_id, request.full_name)
        # Re-fetch to get the canonical workspace context.
        return await self.get_profile(principal)

    async def change_password(self, principal: Principal, request: ChangePasswordRequest) -> None:
        """Verify the current password against users.password_hash, hash
        the new one, and store. OAuth-only users (no password yet) can
        set an initial password via this endpoint by sending the empty
        string for current_password — but the schema requires a
        non-empty current_password, so OAuth-only users have to use a
        future "set initial password" flow. (Out of scope for Phase 2.)"""
        member = await self.members.get_by_id(principal.member_id)
        if member is None or member.user_id is None:
            raise InvalidMemberTypeError("member not found")
        user = await self.users.get_by_id(member.user_id)
        if user is None:  # pragma: no cover - FK invariant
            raise InvalidMemberTypeError("user record missing")
        if user.password_hash is None:
            raise AuthenticationError("password not set on this account")
        if not self.hasher.verify(request.current_password, user.password_hash):
            raise AuthenticationError("current password is incorrect")
        await self.users.update_password(user.id, self.hasher.hash(request.new_password))

    async def get_stats(self, principal: Principal) -> MeStatsResponse:
        stats = await self.members.compute_agent_stats(principal.member_id)
        return MeStatsResponse(
            assigned_count=stats.assigned_count,
            completed_count=stats.completed_count,
            avg_resolution_seconds=stats.avg_resolution_seconds,
            last_activity_at=stats.last_activity_at,
            total_tokens_used=stats.total_tokens_used,
        )
