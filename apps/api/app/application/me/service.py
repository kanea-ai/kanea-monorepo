from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError

from app.application.auth.ports import (
    PasswordHasher,
    TokenService,
    UserRepository,
    WorkspaceRepository,
)
from app.application.auth.service import (
    OWNER_PRIORITY,
    _generate_slug,
    _generate_task_prefix,
)
from app.application.me.ports import MeMemberRepository
from app.application.me.schemas import (
    ChangePasswordRequest,
    CreateMyWorkspaceRequest,
    CreateMyWorkspaceResponse,
    DashboardResponse,
    DashboardScope,
    MeProfileResponse,
    MeStatsResponse,
    MeWorkspaceOption,
    NotificationCountResponse,
    NotificationResponse,
    UpdateMeRequest,
)
from app.application.notifications.ports import NotificationRepository
from app.application.tasks.ports import TaskRepository
from app.application.tasks.schemas import Principal, TaskResponse
from app.domain.entities import Member, Workspace
from app.domain.enums import MemberRole, MemberType, TeamRole
from app.domain.exceptions import (
    AuthenticationError,
    InvalidMemberTypeError,
    NotificationNotFoundError,
    WorkspaceNameConflictError,
)


@dataclass(slots=True)
class MeService:
    users: UserRepository
    members: MeMemberRepository
    workspaces: WorkspaceRepository
    hasher: PasswordHasher
    # Optional so callers that don't exercise the inbox / switcher (a
    # narrower class of unit tests) can omit them.
    notifications: NotificationRepository | None = None
    tokens: TokenService | None = None
    # Phase 5 batch 3: drives the role-scoped /me/dashboard endpoint.
    # Optional so older unit tests that don't exercise the dashboard
    # don't have to wire it.
    tasks: TaskRepository | None = None

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

    # ---------- notifications ----------

    async def list_notifications(
        self, principal: Principal, *, limit: int = 50, offset: int = 0
    ) -> list[NotificationResponse]:
        if self.notifications is None:  # pragma: no cover - DI invariant
            raise RuntimeError("notifications repo not wired")
        member = await self.members.get_by_id(principal.member_id)
        if member is None or member.user_id is None:
            raise InvalidMemberTypeError("member not found")
        rows = await self.notifications.list_for_user(member.user_id, limit=limit, offset=offset)

        # Resolve each actor's display name in one query so the bell
        # can render "Alice mentioned you on TASK-12" without a per-row
        # round-trip on the client.
        actor_ids = {r.source_member_id for r in rows if r.source_member_id is not None}
        actor_names: dict[UUID, str] = {}
        for actor_id in actor_ids:
            actor = await self.members.get_by_id(actor_id)
            if actor is not None:
                actor_names[actor_id] = actor.name

        return [
            NotificationResponse(
                id=row.id,
                type=row.type,
                source_task_id=row.source_task_id,
                source_comment_id=row.source_comment_id,
                source_member_id=row.source_member_id,
                source_member_name=(
                    actor_names.get(row.source_member_id)
                    if row.source_member_id is not None
                    else None
                ),
                preview=row.preview,
                read_at=row.read_at,
                created_at=row.created_at,
            )
            for row in rows
        ]

    async def unread_count(self, principal: Principal) -> NotificationCountResponse:
        if self.notifications is None:  # pragma: no cover
            raise RuntimeError("notifications repo not wired")
        member = await self.members.get_by_id(principal.member_id)
        if member is None or member.user_id is None:
            raise InvalidMemberTypeError("member not found")
        return NotificationCountResponse(
            unread=await self.notifications.unread_count(member.user_id)
        )

    async def mark_notification_read(self, principal: Principal, notification_id: UUID) -> None:
        if self.notifications is None:  # pragma: no cover
            raise RuntimeError("notifications repo not wired")
        member = await self.members.get_by_id(principal.member_id)
        if member is None or member.user_id is None:
            raise InvalidMemberTypeError("member not found")
        rowcount = await self.notifications.mark_read(notification_id, member.user_id)
        if rowcount == 0:
            # Either the notification is owned by someone else, doesn't
            # exist, or is already read. The 404 keeps the API honest
            # for the first two; clients shouldn't double-mark.
            raise NotificationNotFoundError("notification not found")

    async def mark_all_notifications_read(self, principal: Principal) -> int:
        if self.notifications is None:  # pragma: no cover
            raise RuntimeError("notifications repo not wired")
        member = await self.members.get_by_id(principal.member_id)
        if member is None or member.user_id is None:
            raise InvalidMemberTypeError("member not found")
        return await self.notifications.mark_all_read(member.user_id)

    # ---------- workspaces (sidebar switcher / /workspaces page) ----------

    async def list_my_workspaces(self, principal: Principal) -> list[MeWorkspaceOption]:
        """Returns the workspaces the calling user has a membership in.
        Drives both the sidebar dropdown and the /workspaces tile
        picker. Marks the principal's current workspace so the UI can
        render it differently (badge, hide from switcher, etc.)."""
        member = await self.members.get_by_id(principal.member_id)
        if member is None or member.user_id is None:
            raise InvalidMemberTypeError("member not found")

        memberships = await self.members.list_for_user(member.user_id)
        # AGENT rows can't have a user_id (CHECK constraint), but the
        # filter is the belt to that brace.
        memberships = [m for m in memberships if m.type is MemberType.HUMAN]

        out: list[MeWorkspaceOption] = []
        for m in memberships:
            ws = await self.workspaces.get_by_id(m.workspace_id)
            if ws is None:  # pragma: no cover - FK invariant
                continue
            out.append(
                MeWorkspaceOption(
                    workspace_id=ws.id,
                    name=ws.name,
                    role=m.role,
                    member_id=m.id,
                    is_current=ws.id == principal.workspace_id,
                )
            )
        # Stable order: current first, then alphabetical.
        out.sort(key=lambda o: (not o.is_current, o.name.lower()))
        return out

    async def create_my_workspace(
        self, principal: Principal, request: CreateMyWorkspaceRequest
    ) -> CreateMyWorkspaceResponse:
        """Authenticated user mints a new workspace and becomes its
        OWNER. Reuses the same workspace+member seam as registration
        but anchors to the current User row — no User row is created.

        Returns the workspace summary plus an access token bound to
        the new membership so the frontend can swap context immediately
        without bouncing through /auth/select-workspace."""
        if self.tokens is None:  # pragma: no cover - DI invariant
            raise RuntimeError("token service not wired")
        member = await self.members.get_by_id(principal.member_id)
        if member is None or member.user_id is None:
            raise InvalidMemberTypeError("member not found")
        # Re-load the User to get email/full_name for the new Member row.
        user = await self.users.get_by_id(member.user_id)
        if user is None:  # pragma: no cover - FK invariant
            raise InvalidMemberTypeError("user record missing")

        try:
            workspace = await self.workspaces.create(
                Workspace(
                    id=uuid4(),
                    name=request.name,
                    slug=_generate_slug(request.name),
                    task_prefix=_generate_task_prefix(request.name),
                    next_task_seq=1,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
            )
        except IntegrityError as exc:
            raise WorkspaceNameConflictError(
                f"a workspace named {request.name!r} already exists"
            ) from exc

        new_member = await self.members.create(
            Member(
                id=uuid4(),
                workspace_id=workspace.id,
                user_id=user.id,
                type=MemberType.HUMAN,
                name=user.full_name,
                email=user.email,
                priority=OWNER_PRIORITY,
                role=MemberRole.WORKSPACE_OWNER,
            )
        )

        access_token, expires_in = self.tokens.issue_human_token(new_member)
        return CreateMyWorkspaceResponse(
            workspace_id=workspace.id,
            name=workspace.name,
            member_id=new_member.id,
            access_token=access_token,
            expires_in=expires_in,
        )

    # ---------- dashboard ----------

    async def get_dashboard(self, principal: Principal) -> DashboardResponse:
        """Phase 5 batch 3 — role-scoped dashboard data.

        Scope hierarchy:
        - WORKSPACE_OWNER / WORKSPACE_ADMIN: all workspace tasks. The
          spec calls for "all metrics across the entire workspace";
          we don't apply any narrowing.
        - HEAD / MANAGER on a team: team-owned tasks PLUS every task
          in any project the team has work in. Lets a manager see
          cross-team work that affects their projects.
        - LEAD on a team: team-owned tasks only. The team is the unit.
        - MEMBER on a team: tasks assigned to them OR owned by their
          team. Spec: "tasks assigned directly to them or their
          immediate team's queue".
        - Anyone not on a team (and not admin): tasks assigned to
          them. The personal-only fallback.
        """
        if self.tasks is None:  # pragma: no cover - DI invariant
            raise RuntimeError("tasks repo not wired")

        member = await self.members.get_by_id(principal.member_id)
        if member is None or member.workspace_id != principal.workspace_id:
            raise InvalidMemberTypeError("member not found")
        workspace = await self.workspaces.get_by_id(principal.workspace_id)
        if workspace is None:  # pragma: no cover - FK invariant
            raise InvalidMemberTypeError("workspace missing")

        is_admin = principal.role in (
            MemberRole.WORKSPACE_OWNER,
            MemberRole.WORKSPACE_ADMIN,
        )

        scope_label = "Personal"
        scope_member_id: UUID | None = None
        scope_team_id: UUID | None = None
        scope_project_ids: list[UUID] = []

        if is_admin:
            # All-workspace path. Pass no narrowing filters → repo
            # returns everything.
            scope_label = "Workspace"
            tasks = await self.tasks.list_for_dashboard(principal.workspace_id)
        else:
            team_role = member.team_role
            on_team = member.team_id is not None
            if on_team and team_role is TeamRole.MANAGER:
                scope_label = "Projects you oversee"
                scope_team_id = member.team_id
                scope_project_ids = await self.tasks.list_project_ids_for_team(
                    principal.workspace_id, member.team_id  # type: ignore[arg-type]
                )
                tasks = await self.tasks.list_for_dashboard(
                    principal.workspace_id,
                    team_id=member.team_id,
                    project_ids=scope_project_ids,
                )
            elif on_team and team_role == TeamRole.LEAD:
                scope_label = "Your team"
                scope_team_id = member.team_id
                tasks = await self.tasks.list_for_dashboard(
                    principal.workspace_id,
                    team_id=member.team_id,
                )
            elif on_team:
                # Plain MEMBER on a team: own tasks + team queue.
                scope_label = "You + your team"
                scope_member_id = principal.member_id
                scope_team_id = member.team_id
                tasks = await self.tasks.list_for_dashboard(
                    principal.workspace_id,
                    member_id=principal.member_id,
                    team_id=member.team_id,
                )
            else:
                # No team: personal only.
                scope_label = "Your tasks"
                scope_member_id = principal.member_id
                tasks = await self.tasks.list_for_dashboard(
                    principal.workspace_id,
                    member_id=principal.member_id,
                )

        scope = DashboardScope(
            label=scope_label,
            is_admin=is_admin,
            member_id=scope_member_id,
            team_id=scope_team_id,
            project_count=len(scope_project_ids),
        )
        prefix = workspace.task_prefix
        return DashboardResponse(
            scope=scope,
            tasks=[TaskResponse.from_entity(t, prefix=prefix) for t in tasks],
        )
