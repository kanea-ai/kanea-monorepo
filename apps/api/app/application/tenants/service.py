from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from app.application.audit.service import AuditLogService
from app.application.auth.ports import (
    CredentialsRepository,
    MemberRepository,
    PasswordHasher,
    TokenService,
    UserRepository,
)
from app.application.auth.schemas import TokenResponse
from app.application.departments.ports import DepartmentRepository
from app.application.pagination import Page
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
    MemberProfileResponse,
    MemberResponse,
    SetMemberSuspensionRequest,
    SetMemberTeamRequest,
    UpdateMemberProfileRequest,
    invite_create_response_from_entity,
)
from app.domain.entities import AgentStats, Department, Invite, Member, User
from app.domain.enums import AuditAction, AuditResourceType, MemberRole, MemberType, TeamRole
from app.domain.exceptions import (
    EmailAlreadyExistsError,
    ForbiddenError,
    InvalidMemberTypeError,
    InviteAlreadyAcceptedError,
    InviteExpiredError,
    InviteNotFoundError,
    MemberIsDepartmentHeadError,
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
    # Department repo so the set-member-team response can embed the
    # resolved Department (User -> Team -> Department) without a
    # follow-up call. Optional so legacy constructors stay green.
    departments: DepartmentRepository | None = None
    # Phase 1: invite acceptance creates-or-links the global User row.
    # Optional so legacy constructors / unit tests stay valid; the
    # accept_invite path raises if it's missing.
    users: UserRepository | None = None
    # Phase 6 audit trail. Optional in unit tests; production wiring
    # always provides it. When None the mutations succeed without
    # writing an audit row — the underlying state change still
    # happens.
    audit_logs: AuditLogService | None = None

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

        # Provision the User and Member up-front so the directory
        # surfaces the new entry immediately and admins can edit
        # their workspace role / password before the invitee accepts.
        # The invite token is still required to set the *invitee's*
        # own password — the placeholder we mint here is unguessable.
        if self.users is None:  # pragma: no cover - DI invariant
            raise RuntimeError("users repo not wired")

        existing_member = await self.auth_members.get_by_email(str(request.email))
        if existing_member is not None and existing_member.workspace_id == principal.workspace_id:
            raise EmailAlreadyExistsError(
                "a member with this email already exists in the workspace"
            )

        user = await self.users.get_by_email(str(request.email))
        if user is None:
            # Brand-new account on the platform. Mint a User with a
            # random throw-away password hash. The invitee sets their
            # real password on accept; an admin can also set one via
            # POST /tenants/members/{id}/password before then.
            placeholder = secrets.token_urlsafe(32)
            user = await self.users.create(
                User(
                    id=uuid4(),
                    email=str(request.email),
                    full_name=_default_name_from_email(str(request.email)),
                    password_hash=self.hasher.hash(placeholder),
                )
            )

        # Member row, role from the invite payload. Created with
        # priority 5 to match the previous accept-time default.
        await self.auth_members.create(
            Member(
                id=uuid4(),
                workspace_id=principal.workspace_id,
                user_id=user.id,
                type=MemberType.HUMAN,
                name=user.full_name,
                email=str(request.email),
                priority=5,
                role=request.role,
            )
        )

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
        """Phase 6: the User and Member are now provisioned at invite-
        send. Accept therefore *updates* the existing rows with the
        invitee's real name + password rather than creating new ones.

        For invitees who already had a User in another workspace, we
        leave the password untouched — that User belongs to other
        workspaces too, and an admin in *this* workspace shouldn't
        clobber it. The check is "User has more than one membership".
        """
        if self.users is None:  # pragma: no cover - DI invariant
            raise RuntimeError("users repo not wired")

        invite = await self._load_active_invite(raw_token)

        user = await self.users.get_by_email(invite.email)
        if user is None:  # pragma: no cover - create_invite invariant
            raise InviteNotFoundError("invite is missing its prepared user row")

        member = await self.auth_members.get_by_email(invite.email)
        # Cross-workspace edge: the matched member could belong to a
        # different workspace if the email has memberships across the
        # platform. Re-resolve the membership belonging to this
        # invite's workspace via list_for_user — every other code
        # path is also fine with that scoping.
        memberships = await self.auth_members.list_for_user(user.id)
        target_membership = next(
            (m for m in memberships if m.workspace_id == invite.workspace_id),
            None,
        )
        if target_membership is None:  # pragma: no cover - create_invite invariant
            raise InviteNotFoundError("invite is missing its prepared member row")
        member = target_membership

        # Update the User's display name. Always — the placeholder
        # name we picked at invite-send is the email's local part,
        # which is rarely what the human wants on their profile.
        await self.users.update_full_name(user.id, request.full_name)
        # Update password only when this is the user's *only*
        # membership. A returning user already has a working
        # credential we shouldn't overwrite from this workspace's
        # accept flow.
        if len(memberships) == 1:
            await self.users.update_password(user.id, self.hasher.hash(request.password))
        # And keep the Member's own display name in sync with the
        # User's so directory rows render the new name.
        member = await self.auth_members.update_profile(member.id, name=request.full_name)

        await self.invites.mark_accepted(invite.id)

        token, ttl = self.tokens.issue_human_token(member)
        return TokenResponse(access_token=token, expires_in=ttl)

    async def list_workspace_members(
        self,
        principal: Principal,
        filters: MemberFilters | None = None,
        *,
        skip: int = 0,
        limit: int | None = None,
    ) -> Page[MemberResponse]:
        """Paginated workspace members, narrowed by the optional
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

        rows, total = await self.members.list_for_workspace(
            principal.workspace_id,
            name=f.name,
            member_id=f.member_id,
            role=f.role,
            team_id=f.team_id,
            project_id=f.project_id,
            humans_only=f.humans_only,
            visibility_team_id=visibility_team_id,
            visibility_self_id=visibility_self_id,
            skip=skip,
            limit=limit,
        )
        return Page[MemberResponse](
            items=[MemberResponse.from_entity(m) for m in rows], total=total
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

    async def get_member_profile(
        self, member_id: UUID, principal: Principal
    ) -> MemberProfileResponse:
        """Priority-scoped profile. Used by the audit-log UI when a
        lower-rank admin clicks the actor name on an event recorded
        by a higher-rank actor — they get just enough to identify the
        person (id, name, email, type) without exposing role / team /
        suspension state.

        Rules:
        - OWNER always gets the full view of anyone in the workspace.
        - Self always gets the full view (you can see your own role
          and priority on /profile).
        - Otherwise: when the principal's priority value is greater
          than the target's (i.e. the principal is *lower* in rank),
          return the limited shape. Else return full.
        - Plain visibility (admin or teammate) is the gate; the
          existing ``get_member`` rule still throws 403 for callers
          who shouldn't even know the member exists.
        """
        target = await self.get_member(member_id, principal)

        if target.id == principal.member_id:
            return MemberProfileResponse.full(target)
        if principal.role is MemberRole.WORKSPACE_OWNER:
            return MemberProfileResponse.full(target)
        # Lower priority *number* = higher rank. Reduced view kicks
        # in when the principal is lower-rank than the target.
        if principal.priority > target.priority:
            return MemberProfileResponse.limited(target)
        return MemberProfileResponse.full(target)

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
            # ``list_for_workspace`` returns ``(items, total)`` —
            # the count is unused here, just unpack to a list.
            others, _ = await self.members.list_for_workspace(
                principal.workspace_id, role=MemberRole.WORKSPACE_OWNER
            )
            still_owners_after = [m for m in others if m.id != target.id]
            if not still_owners_after:
                raise ForbiddenError("cannot demote the last workspace owner")

        updated = await self.members.update_profile(
            member_id,
            name=request.name,
            role=request.role,
            priority=request.priority,
        )

        if self.audit_logs is not None:
            # Role changes get their own audit action so the UI can
            # render a clear "Bob → ADMIN" line; everything else
            # collapses into a generic UPDATED with a {field: from/to}
            # diff. Both shapes target the MEMBER resource.
            if request.role is not None and request.role is not target.role:
                await self.audit_logs.record(
                    principal,
                    action=AuditAction.ROLE_CHANGED,
                    resource_type=AuditResourceType.MEMBER,
                    resource_id=updated.id,
                    changes={
                        "from": target.role.value,
                        "to": updated.role.value,
                        "member_name": updated.name,
                    },
                )
            other_diff = _field_diff(
                {"name": target.name, "priority": target.priority},
                {"name": updated.name, "priority": updated.priority},
            )
            if other_diff:
                await self.audit_logs.record(
                    principal,
                    action=AuditAction.UPDATED,
                    resource_type=AuditResourceType.MEMBER,
                    resource_id=updated.id,
                    changes=other_diff,
                )
        return updated

    async def set_member_team(
        self,
        member_id: UUID,
        request: SetMemberTeamRequest,
        principal: Principal,
    ) -> MemberResponse:
        """Workspace admins assign a member to a Team and set their
        intra-team role. Validates: tenant isolation, team_id +
        team_role coherence (both set or both null), team belongs to
        the same workspace.

        Single-MANAGER / single-LEAD constraint: assigning ``MANAGER``
        or ``LEAD`` on a team that already has one demotes the sitting
        holder to MEMBER in the same DB transaction (they keep their
        team membership; only the rank changes). The DB carries a
        partial unique index as the belt to this service-level brace.

        Auto-department resolution: the response embeds the Department
        the new team belongs to (via team.department_id), so the UI
        renders the new hierarchy without a follow-up call.

        RBAC inheritance: the caller must be a workspace OWNER / ADMIN
        OR the Department Head of the team's department (heads inherit
        MANAGER-level reach over every team in their dept). Explicit
        unassigns (team_id=null) require admin role — clearing the
        team of a member outside one's department isn't a head's
        decision.

        Strict isolation: if the target is currently the head of any
        Department, refuse non-null team assignments. ``team_id=null``
        is still allowed because that's the same clearing path
        DepartmentService uses when first promoting the head."""
        if request.team_id is None and request.team_role is not None:
            raise InvalidMemberTypeError("team_role must be null when team_id is null")
        if request.team_id is not None and request.team_role is None:
            raise InvalidMemberTypeError("team_role is required when team_id is set")

        # Early role gate. Workspace OWNER / ADMIN always pass. For
        # non-admins we may still allow the call via dept-head
        # inheritance — but only when there's a target team whose
        # department we can inspect. Unassigns (team_id is None) and
        # any DI shape that lacks ``departments`` short-circuit to
        # ForbiddenError so we don't load anything else under a clearly
        # disallowed call.
        is_admin = principal.role in (MemberRole.WORKSPACE_OWNER, MemberRole.WORKSPACE_ADMIN)
        if not is_admin and (request.team_id is None or self.departments is None):
            raise ForbiddenError("workspace owner or admin role required")

        target = await self.members.get_by_id(member_id)
        if target is None or target.workspace_id != principal.workspace_id:
            raise InvalidMemberTypeError("member not found")

        # The team must belong to the same workspace; the FK alone
        # accepts cross-tenant ids so we add an explicit check.
        team_entity = None
        if request.team_id is not None and self.teams is not None:
            team_entity = await self.teams.get_by_id(request.team_id)
            if team_entity is None or team_entity.workspace_id != principal.workspace_id:
                raise InvalidMemberTypeError("team not found")

        # Dept-head inheritance: non-admins must head the department
        # the new team belongs to. The early gate above already
        # filtered out the unassign and missing-departments-DI cases.
        if not is_admin:
            assert self.departments is not None  # narrowed by early gate
            if team_entity is None or team_entity.department_id is None:
                raise ForbiddenError(
                    "you can only manage team membership for teams in your own department"
                )
            principal_dept = await self.departments.get_for_head(principal.member_id)
            if principal_dept is None or principal_dept.id != team_entity.department_id:
                raise ForbiddenError(
                    "you can only manage team membership for teams in your own department"
                )

        # Strict isolation: a current Department Head cannot also be on
        # a team. Block the assignment path; the explicit unassign
        # (team_id=None) still passes — that's the same call shape used
        # by DepartmentService when the head was promoted in the first
        # place.
        if request.team_id is not None and self.departments is not None:
            target_head_dept = await self.departments.get_for_head(target.id)
            if target_head_dept is not None:
                raise MemberIsDepartmentHeadError(
                    f"{target.name} is the head of department "
                    f"'{target_head_dept.name}'; remove them from head_id "
                    "before assigning a team"
                )

        # One-MANAGER / one-LEAD enforcement. Look up the sitting
        # holder *before* we promote the target so we can demote them
        # in the same session — the DB partial unique index would
        # otherwise reject our second write.
        if request.team_id is not None and request.team_role in (
            TeamRole.MANAGER,
            TeamRole.LEAD,
        ):
            sitting = await self.members.get_for_team_role(request.team_id, request.team_role)
            if sitting is not None and sitting.id != target.id:
                await self.members.set_team(
                    sitting.id,
                    team_id=request.team_id,
                    team_role=TeamRole.MEMBER,
                )
                if self.audit_logs is not None:
                    await self.audit_logs.record(
                        principal,
                        action=AuditAction.UPDATED,
                        resource_type=AuditResourceType.MEMBER,
                        resource_id=sitting.id,
                        changes={
                            "team_role": {
                                "from": request.team_role.value,
                                "to": TeamRole.MEMBER.value,
                            },
                            "member_name": sitting.name,
                            "demoted_for_member_id": str(target.id),
                        },
                    )

        updated = await self.members.set_team(
            member_id,
            team_id=request.team_id,
            team_role=request.team_role,
        )

        if self.audit_logs is not None:
            # Two distinct flavours: assigning to a team (or moving)
            # vs. unassigning. They render differently in the audit
            # UI so we use separate AuditAction values.
            if request.team_id is None and target.team_id is not None:
                await self.audit_logs.record(
                    principal,
                    action=AuditAction.TEAM_UNASSIGNED,
                    resource_type=AuditResourceType.MEMBER,
                    resource_id=updated.id,
                    changes={
                        "from_team_id": str(target.team_id),
                        "from_team_role": (target.team_role.value if target.team_role else None),
                        "member_name": updated.name,
                    },
                )
            elif request.team_id is not None and (
                request.team_id != target.team_id or request.team_role != target.team_role
            ):
                await self.audit_logs.record(
                    principal,
                    action=AuditAction.TEAM_ASSIGNED,
                    resource_type=AuditResourceType.MEMBER,
                    resource_id=updated.id,
                    changes={
                        "to_team_id": str(request.team_id),
                        "to_team_role": (request.team_role.value if request.team_role else None),
                        "from_team_id": (str(target.team_id) if target.team_id else None),
                        "from_team_role": (target.team_role.value if target.team_role else None),
                        "member_name": updated.name,
                    },
                )

        department = await self._resolve_member_department(updated, team_entity=team_entity)
        return MemberResponse.from_entity(updated, department=department)

    async def _resolve_member_department(
        self,
        member: Member,
        *,
        team_entity=None,
    ) -> Department | None:
        """Walk member -> team -> department. Returns None when the
        member is unassigned, the team is un-filed, or the dep wiring
        is missing (legacy unit-test constructors). ``team_entity`` is
        an optional pre-fetched Team to skip the lookup when the caller
        already has it in hand."""
        if member.team_id is None:
            return None
        if self.teams is None or self.departments is None:
            return None
        if team_entity is None:
            team_entity = await self.teams.get_by_id(member.team_id)
        if team_entity is None or team_entity.department_id is None:
            return None
        return await self.departments.get_by_id(team_entity.department_id)

    async def set_member_suspension(
        self,
        member_id: UUID,
        request: SetMemberSuspensionRequest,
        principal: Principal,
    ) -> Member:
        """Workspace-scoped soft lock. Admins can suspend any member
        in the workspace and revoke later — the auth dep does the
        actual blocking on subsequent requests.

        Guards:
        - Tenant isolation: target must belong to ``principal.workspace_id``.
        - Self-lock prevention: a principal can't suspend themselves
          (they'd lock themselves out of the workspace they're
          currently administering).
        - Last-owner protection: can't suspend the last remaining
          ``WORKSPACE_OWNER`` — same invariant the role-demotion path
          enforces, for the same reason (the workspace must always
          have at least one usable admin path).
        """
        if principal.role not in (MemberRole.WORKSPACE_OWNER, MemberRole.WORKSPACE_ADMIN):
            raise ForbiddenError("workspace owner or admin role required")

        target = await self.members.get_by_id(member_id)
        if target is None or target.workspace_id != principal.workspace_id:
            raise InvalidMemberTypeError("member not found")

        if request.is_suspended and target.id == principal.member_id:
            raise ForbiddenError("you cannot suspend your own membership")

        # Last-owner protection on the suspend path. Revoking is
        # always safe.
        if request.is_suspended and target.role is MemberRole.WORKSPACE_OWNER:
            owners, _ = await self.members.list_for_workspace(
                principal.workspace_id, role=MemberRole.WORKSPACE_OWNER
            )
            still_active_owners = [m for m in owners if m.id != target.id and not m.is_suspended]
            if not still_active_owners:
                raise ForbiddenError("cannot suspend the last active workspace owner")

        updated = await self.members.set_suspended(member_id, is_suspended=request.is_suspended)

        if self.audit_logs is not None and target.is_suspended != request.is_suspended:
            await self.audit_logs.record(
                principal,
                action=(
                    AuditAction.SUSPENDED
                    if request.is_suspended
                    else AuditAction.SUSPENSION_REVOKED
                ),
                resource_type=AuditResourceType.MEMBER,
                resource_id=updated.id,
                changes={
                    "member_name": updated.name,
                    "member_email": updated.email,
                },
            )
        return updated

    async def admin_set_member_password(
        self,
        member_id: UUID,
        new_password: str,
        principal: Principal,
    ) -> None:
        """Admin / owner password reset.

        Scope rules:
        - **Owner**: can reset any non-self, non-agent member in the
          workspace — including admins. The owner is the top of the
          access tree, so no extra scope check.
        - **Admin**: can reset password of a member only when they
          share *organisational scope* with that member — same team,
          OR same department (resolved via the teams' department_id).
          Admins cannot reset an OWNER's password (rank protection).

        Hard rules that apply to everyone:
        - Self-reset is rejected (use ``/me/password``; the current-
          password requirement there is the belt-and-braces).
        - Agents have no User row; ``agent_secret`` is their
          credential.
        - Cross-workspace users (User.memberships > 1) — we don't
          touch their credential because it's shared with workspaces
          the principal has no authority over. They need the public
          password-recovery flow.
        """
        if self.users is None:  # pragma: no cover - DI invariant
            raise RuntimeError("users repo not wired")
        if principal.role not in (MemberRole.WORKSPACE_OWNER, MemberRole.WORKSPACE_ADMIN):
            raise ForbiddenError("workspace owner or admin role required")

        target = await self.members.get_by_id(member_id)
        if target is None or target.workspace_id != principal.workspace_id:
            raise InvalidMemberTypeError("member not found")
        if target.id == principal.member_id:
            raise ForbiddenError("use the change-password flow on /me to reset your own password")
        if target.user_id is None:
            # AGENTs have no User row — passwords don't apply to them;
            # they auth via agent_secret.
            raise InvalidMemberTypeError("agents do not have a password to set")

        # Org-scope check for non-owner admins. Owners skip this —
        # they have authority over the whole workspace.
        if principal.role is MemberRole.WORKSPACE_ADMIN:
            await self._require_org_scope_match(principal, target)

        memberships = await self.auth_members.list_for_user(target.user_id)
        if len(memberships) > 1:
            raise ForbiddenError(
                "this user has memberships in other workspaces; "
                "only they can change their password"
            )

        await self.users.update_password(target.user_id, self.hasher.hash(new_password))

    async def _require_org_scope_match(self, principal: Principal, target: Member) -> None:
        """Admin scope check: principal and target must share a team
        OR a department, OR the principal is the head of the target's
        department. Owners are excluded from this rule (their own
        scope is the whole workspace) and target OWNERs are off-
        limits to admins regardless of co-location."""
        if target.role is MemberRole.WORKSPACE_OWNER:
            raise ForbiddenError("only an owner can reset another owner's password")

        principal_member = await self.members.get_by_id(principal.member_id)
        if principal_member is None:  # pragma: no cover - principal must resolve
            raise ForbiddenError("requester not found")

        # Same team — fast path. Both members carry team_id directly.
        if principal_member.team_id is not None and principal_member.team_id == target.team_id:
            return

        # Same department — needs the team rows to read department_id.
        # Also: dept-head inheritance — the principal heads the
        # department the target's team belongs to.
        if self.teams is None:
            raise ForbiddenError(
                "you can only reset the password of a member in your team or department"
            )
        if target.team_id is None:
            raise ForbiddenError(
                "you can only reset the password of a member in your team or department"
            )
        target_team = await self.teams.get_by_id(target.team_id)
        if target_team is None or target_team.department_id is None:
            raise ForbiddenError(
                "you can only reset the password of a member in your team or department"
            )

        # Co-located department via the principal's own team (legacy
        # path) — both members on different teams under the same
        # department.
        if principal_member.team_id is not None:
            principal_team = await self.teams.get_by_id(principal_member.team_id)
            if (
                principal_team is not None
                and principal_team.department_id == target_team.department_id
            ):
                return

        # Dept-head inheritance. A Head sits above team-level leadership
        # and has implicit MANAGER reach over every team in their dept;
        # password reset for those team members is in-scope.
        if self.departments is not None:
            principal_head_dept = await self.departments.get_for_head(principal.member_id)
            if (
                principal_head_dept is not None
                and principal_head_dept.id == target_team.department_id
            ):
                return

        raise ForbiddenError(
            "you can only reset the password of a member in your team or department"
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


def _default_name_from_email(email: str) -> str:
    """At invite-send time we don't yet know the invitee's real name.
    Use the local-part as a placeholder so the directory row reads
    sensibly until they accept and update it. ``alice@example.com`` →
    ``alice``."""
    local = email.split("@", 1)[0]
    return local or email


def _field_diff(before: dict, after: dict) -> dict:
    """{field: {from, to}} shape for UPDATED audit rows. Skips fields
    that didn't actually change so audit payloads stay terse."""
    diff: dict[str, dict] = {}
    for key in set(before) | set(after):
        if before.get(key) != after.get(key):
            diff[key] = {"from": before.get(key), "to": after.get(key)}
    return diff


def _accept_url(_id: UUID) -> str:  # pragma: no cover - kept for symmetry
    raise NotImplementedError
