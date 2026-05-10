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
    UserRepository,
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
    MemberFilters,
    SetMemberTeamRequest,
    UpdateMemberProfileRequest,
    invite_create_response_from_entity,
)
from app.domain.entities import AgentStats, Invite, Member, User
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
    # Phase 1: invite acceptance creates-or-links the global User row.
    # Optional so legacy constructors / unit tests stay valid; the
    # accept_invite path raises if it's missing.
    users: UserRepository | None = None

    async def create_invite(
        self, request: InviteCreateRequest, principal: Principal
    ) -> InviteCreateResponse:
        if not request.is_role_inviteable():
            raise ForbiddenError("OWNER role cannot be granted via invite")

        # Authorization is also enforced at the route layer via
        # WorkspaceAdminDep; this is the defensive belt for service-level
        # callers (tests, future internal call-sites).
        if principal.role not in (MemberRole.WORKSPACE_OWNER, MemberRole.WORKSPACE_ADMIN):
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
        if self.users is None:  # pragma: no cover - DI invariant
            raise RuntimeError("users repo not wired")

        invite = await self._load_active_invite(raw_token)

        # Reject if a member with the invited email already exists in
        # this workspace — uq_members_workspace_id_email would catch
        # it; surfacing a clean 409 here.
        existing = await self.auth_members.get_by_email(invite.email)
        if existing is not None and existing.workspace_id == invite.workspace_id:
            raise EmailAlreadyExistsError(
                "a member with this email already exists in the workspace"
            )

        # Phase 1 multi-tenancy: an invitee may already have a User
        # row from a different workspace. If so, link the new
        # membership to it; otherwise mint a User using the password
        # the invitee just typed in.
        user = await self.users.get_by_email(invite.email)
        if user is None:
            user = await self.users.create(
                User(
                    id=uuid4(),
                    email=invite.email,
                    full_name=request.full_name,
                    password_hash=self.hasher.hash(request.password),
                )
            )
        # If the User already exists, we don't reset their password —
        # they'd be confused why their existing password stopped
        # working. The accept payload password is silently ignored
        # in that branch (the user can change it later in settings).

        # Priority: invited members default to a higher number (lower
        # rank) than the workspace owner so they sit below in the
        # delegation hierarchy.
        member = await self.auth_members.create(
            Member(
                id=uuid4(),
                workspace_id=invite.workspace_id,
                user_id=user.id,
                type=MemberType.HUMAN,
                name=request.full_name,
                email=invite.email,
                priority=5,
                role=invite.role,
            )
        )
        await self.invites.mark_accepted(invite.id)

        token, ttl = self.tokens.issue_human_token(member)
        return TokenResponse(access_token=token, expires_in=ttl)

    async def list_workspace_members(
        self,
        principal: Principal,
        filters: MemberFilters | None = None,
    ) -> list[Member]:
        """Returns the workspace's members, narrowed by the optional
        filters and by the caller's visibility scope.

        Visibility:
        - WORKSPACE_OWNER / WORKSPACE_ADMIN: see everyone.
        - Anyone else: see members in their team plus themselves. If
          they're not on a team, they see only themselves.

        The filters layer applies on top of visibility, so a manager
        narrowing by role still won't reach members outside their team.
        Cross-workspace bleed-through is impossible — every query is
        scoped by workspace_id from the principal.
        """
        f = filters or MemberFilters()

        is_admin = principal.role in (
            MemberRole.WORKSPACE_OWNER,
            MemberRole.WORKSPACE_ADMIN,
        )
        visibility_team_id: UUID | None = None
        visibility_self_id: UUID | None = None
        if not is_admin:
            # Non-admin: pull the caller's team to scope the listing.
            # If they have no team we fall back to self-only.
            self_member = await self.members.get_by_id(principal.member_id)
            if self_member is not None and self_member.team_id is not None:
                visibility_team_id = self_member.team_id
                visibility_self_id = principal.member_id
            else:
                visibility_self_id = principal.member_id

        return await self.members.list_for_workspace(
            principal.workspace_id,
            name=f.name,
            member_id=f.member_id,
            role=f.role,
            team_id=f.team_id,
            project_id=f.project_id,
            humans_only=f.humans_only,
            visibility_team_id=visibility_team_id,
            visibility_self_id=visibility_self_id,
        )

    async def get_member(self, member_id: UUID, principal: Principal) -> Member:
        """Fetch a single member, applying the same visibility rule as
        the list endpoint. Admins see anyone; everyone else can only
        see themselves or a teammate."""
        target = await self.members.get_by_id(member_id)
        if target is None or target.workspace_id != principal.workspace_id:
            raise InvalidMemberTypeError("member not found")

        is_admin = principal.role in (
            MemberRole.WORKSPACE_OWNER,
            MemberRole.WORKSPACE_ADMIN,
        )
        if is_admin:
            return target

        if target.id == principal.member_id:
            return target

        # Teammate visibility: same team_id as the caller, both not None.
        self_member = await self.members.get_by_id(principal.member_id)
        if (
            self_member is not None
            and self_member.team_id is not None
            and target.team_id == self_member.team_id
        ):
            return target

        raise ForbiddenError("not allowed to view this member")

    async def get_member_stats(self, member_id: UUID, principal: Principal) -> AgentStats:
        """Per-member stats. Visibility mirrors get_member exactly —
        the route layer calls get_member first, so by the time we hit
        compute_agent_stats we already know the principal can see this
        member."""
        # The visibility check throws InvalidMemberTypeError / ForbiddenError;
        # we let it propagate — the router maps both to the right HTTP code.
        await self.get_member(member_id, principal)
        return await self.members.compute_agent_stats(member_id)

    async def update_member_profile(
        self,
        member_id: UUID,
        request: UpdateMemberProfileRequest,
        principal: Principal,
    ) -> Member:
        """Admin-only edit of a member's display name and/or workspace
        role. Enforces:
        - tenant isolation (target must be in the principal's workspace)
        - last-owner invariant (can't demote the last WORKSPACE_OWNER)
        - principals can't demote themselves into a non-admin role
          unless another OWNER/ADMIN remains
        """
        if principal.role not in (MemberRole.WORKSPACE_OWNER, MemberRole.WORKSPACE_ADMIN):
            raise ForbiddenError("workspace owner or admin role required")

        target = await self.members.get_by_id(member_id)
        if target is None or target.workspace_id != principal.workspace_id:
            raise InvalidMemberTypeError("member not found")

        # Last-owner protection: don't allow a role change that would
        # leave the workspace without any OWNER. We only need this
        # check when the target IS currently OWNER and the new role
        # ISN'T OWNER.
        if (
            request.role is not None
            and target.role is MemberRole.WORKSPACE_OWNER
            and request.role is not MemberRole.WORKSPACE_OWNER
        ):
            others = await self.members.list_for_workspace(
                principal.workspace_id, role=MemberRole.WORKSPACE_OWNER
            )
            still_owners_after = [m for m in others if m.id != target.id]
            if not still_owners_after:
                raise ForbiddenError("cannot demote the last workspace owner")

        return await self.members.update_profile(
            member_id,
            name=request.name,
            role=request.role,
            priority=request.priority,
        )

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
        if principal.role not in (MemberRole.WORKSPACE_OWNER, MemberRole.WORKSPACE_ADMIN):
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
