from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from app.application.auth.ports import (
    CredentialsRepository,
    MemberRepository,
    PasswordHasher,
    TokenService,
)
from app.application.auth.schemas import TokenResponse
from app.application.tasks.schemas import Principal
from app.application.teams.ports import TeamRepository
from app.application.tenants.ports import (
    InviteRepository,
    TenantMemberRepository,
    WorkspaceReadRepository,
)
from app.application.tenants.schemas import (
    InviteAcceptRequest,
    InviteCreateRequest,
    InviteCreateResponse,
    InvitePreviewResponse,
    SetMemberTeamRequest,
    invite_create_response_from_entity,
)
from app.domain.entities import Credentials, Invite, Member
from app.domain.enums import MemberRole, MemberType
from app.domain.exceptions import (
    EmailAlreadyExistsError,
    ForbiddenError,
    InvalidMemberTypeError,
    InviteAlreadyAcceptedError,
    InviteExpiredError,
    InviteNotFoundError,
)

INVITE_TTL_DAYS = 7


def _hash_token(raw: str) -> str:
    """SHA-256 hex of the raw token. We store the hash so a DB leak alone
    doesn't grant access — would-be attackers also need the original
    token (which is only ever in the inviter's hands and the URL bar)."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class InviteService:
    invites: InviteRepository
    members: TenantMemberRepository
    workspaces: WorkspaceReadRepository
    # Auth-side dependencies for the accept flow.
    auth_members: MemberRepository
    credentials: CredentialsRepository
    hasher: PasswordHasher
    tokens: TokenService
    # Public base URL the invite link resolves on. Injected from settings.
    accept_url_base: str
    # Team repo for the team-assignment endpoint. Optional so existing
    # constructors / unit tests stay green.
    teams: TeamRepository | None = None

    async def create_invite(
        self, request: InviteCreateRequest, principal: Principal
    ) -> InviteCreateResponse:
        if not request.is_role_inviteable():
            raise ForbiddenError("OWNER role cannot be granted via invite")

        # Authorization is also enforced at the route layer via
        # WorkspaceAdminDep; this is the defensive belt for service-level
        # callers (tests, future internal call-sites).
        if principal.role not in (MemberRole.OWNER, MemberRole.ADMIN):
            raise ForbiddenError("workspace owner or admin role required")

        raw_token = secrets.token_urlsafe(32)
        invite = await self.invites.create(
            Invite(
                id=uuid4(),
                workspace_id=principal.workspace_id,
                invited_by_id=principal.member_id,
                email=str(request.email),
                role=request.role,
                token_hash=_hash_token(raw_token),
                expires_at=datetime.utcnow() + timedelta(days=INVITE_TTL_DAYS),
            )
        )

        accept_url = f"{self.accept_url_base.rstrip('/')}/invite/{raw_token}"
        return invite_create_response_from_entity(
            invite, raw_token=raw_token, accept_url=accept_url
        )

    async def get_invite_preview(self, raw_token: str) -> InvitePreviewResponse:
        invite = await self._load_active_invite(raw_token)
        workspace = await self.workspaces.get_by_id(invite.workspace_id)
        if workspace is None:  # pragma: no cover - DB invariant
            raise InviteNotFoundError("invite points at a missing workspace")

        return InvitePreviewResponse(
            workspace_name=workspace.name,
            email=invite.email,
            role=invite.role,
            expires_at=invite.expires_at,
        )

    async def accept_invite(self, raw_token: str, request: InviteAcceptRequest) -> TokenResponse:
        invite = await self._load_active_invite(raw_token)

        # Reject if a member with the invited email already exists in this
        # workspace — would violate uq_members_workspace_id_email anyway,
        # surface a clearer error here.
        existing = await self.auth_members.get_by_email(invite.email)
        if existing is not None and existing.workspace_id == invite.workspace_id:
            raise EmailAlreadyExistsError(
                "a member with this email already exists in the workspace"
            )

        # Priority: invited members default to a higher number (lower rank)
        # than the workspace owner so they sit below in the delegation
        # hierarchy. Owner is priority=1 by signup; we use 5 here, leaving
        # 2-4 for explicit role tiers later.
        member = await self.auth_members.create(
            Member(
                id=uuid4(),
                workspace_id=invite.workspace_id,
                type=MemberType.HUMAN,
                name=request.full_name,
                email=invite.email,
                priority=5,
                role=invite.role,
            )
        )
        await self.credentials.create(
            Credentials(
                id=uuid4(),
                member_id=member.id,
                password_hash=self.hasher.hash(request.password),
                agent_secret_hash=None,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        )
        await self.invites.mark_accepted(invite.id)

        token, ttl = self.tokens.issue_human_token(member)
        return TokenResponse(access_token=token, expires_in=ttl)

    async def list_workspace_members(self, principal: Principal) -> list[Member]:
        return await self.members.list_for_workspace(principal.workspace_id)

    async def set_member_team(
        self,
        member_id: UUID,
        request: SetMemberTeamRequest,
        principal: Principal,
    ) -> Member:
        """Workspace admins assign a member to a Team and set their
        intra-team role. Validates: tenant isolation, team_id +
        team_role coherence (both set or both null), team belongs to
        the same workspace.

        Route-level RBAC (WorkspaceAdminDep) is the primary guard;
        this service-level check is the belt for direct callers."""
        if principal.role not in (MemberRole.OWNER, MemberRole.ADMIN):
            raise ForbiddenError("workspace owner or admin role required")

        if request.team_id is None and request.team_role is not None:
            raise InvalidMemberTypeError("team_role must be null when team_id is null")
        if request.team_id is not None and request.team_role is None:
            raise InvalidMemberTypeError("team_role is required when team_id is set")

        target = await self.members.get_by_id(member_id)
        if target is None or target.workspace_id != principal.workspace_id:
            raise InvalidMemberTypeError("member not found")

        # The team must belong to the same workspace; the FK alone
        # accepts cross-tenant ids so we add an explicit check.
        if request.team_id is not None and self.teams is not None:
            team = await self.teams.get_by_id(request.team_id)
            if team is None or team.workspace_id != principal.workspace_id:
                raise InvalidMemberTypeError("team not found")

        return await self.members.set_team(
            member_id,
            team_id=request.team_id,
            team_role=request.team_role,
        )

    async def _load_active_invite(self, raw_token: str) -> Invite:
        invite = await self.invites.get_by_token_hash(_hash_token(raw_token))
        if invite is None:
            raise InviteNotFoundError("invite not found")
        if invite.accepted_at is not None:
            raise InviteAlreadyAcceptedError("invite already accepted")
        # invite.expires_at comes back as timezone-aware from Postgres
        # (TIMESTAMPTZ). Use a tz-aware "now" so we don't trip Python's
        # naive-vs-aware comparison error.
        from datetime import UTC

        now = datetime.now(UTC)
        expires_at = invite.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= now:
            raise InviteExpiredError("invite has expired")
        return invite


def _accept_url(_id: UUID) -> str:  # pragma: no cover - kept for symmetry
    raise NotImplementedError
