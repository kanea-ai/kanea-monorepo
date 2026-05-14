from __future__ import annotations

from functools import lru_cache
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.agents.ports import AgentMemberRepository
from app.application.agents.service import AgentService
from app.application.audit.ports import AuditLogRepository
from app.application.audit.service import AuditLogService
from app.application.auth.oauth import (
    GitHubOAuthClient,
    GoogleOAuthClient,
    OAuthClient,
)
from app.application.auth.ports import (
    CredentialsRepository,
    MemberRepository,
    PasswordHasher,
    TokenService,
    UserRepository,
    WorkspaceRepository,
)
from app.application.auth.service import AuthService
from app.application.departments.ports import DepartmentRepository
from app.application.departments.service import DepartmentService
from app.application.me.ports import MeMemberRepository
from app.application.me.service import MeService
from app.application.notifications.ports import (
    MentionMemberLookup,
    NotificationRepository,
)
from app.application.notifications.service import NotificationService
from app.application.projects.ports import ProjectRepository
from app.application.projects.service import ProjectService
from app.application.tasks.ports import (
    TaskActivityRepository,
    TaskCommentRepository,
    TaskRatingRepository,
    TaskRelationRepository,
    TaskRepository,
    TaskRequestRepository,
    WorkspaceTaskSeqRepository,
)
from app.application.tasks.schemas import Principal
from app.application.tasks.service import TaskService
from app.application.teams.ports import TeamRepository
from app.application.teams.service import TeamService
from app.application.tenants.ports import (
    InviteRepository,
    TenantMemberRepository,
    WorkspaceReadRepository,
)
from app.application.tenants.service import InviteService
from app.application.workspaces.ports import WorkspaceWriteRepository
from app.application.workspaces.service import WorkspaceService
from app.core.config import Settings, settings
from app.domain.enums import MemberRole, MemberType, OAuthProvider
from app.infrastructure.db.session import get_session
from app.infrastructure.repositories.audit_log import SqlAlchemyAuditLogRepository
from app.infrastructure.repositories.credentials import SqlAlchemyCredentialsRepository
from app.infrastructure.repositories.department import SqlAlchemyDepartmentRepository
from app.infrastructure.repositories.invite import SqlAlchemyInviteRepository
from app.infrastructure.repositories.member import SqlAlchemyMemberRepository
from app.infrastructure.repositories.notification import SqlAlchemyNotificationRepository
from app.infrastructure.repositories.project import SqlAlchemyProjectRepository
from app.infrastructure.repositories.task import SqlAlchemyTaskRepository
from app.infrastructure.repositories.task_activity import SqlAlchemyTaskActivityRepository
from app.infrastructure.repositories.task_comment import SqlAlchemyTaskCommentRepository
from app.infrastructure.repositories.task_rating import SqlAlchemyTaskRatingRepository
from app.infrastructure.repositories.task_relation import SqlAlchemyTaskRelationRepository
from app.infrastructure.repositories.task_request import SqlAlchemyTaskRequestRepository
from app.infrastructure.repositories.team import SqlAlchemyTeamRepository
from app.infrastructure.repositories.user import SqlAlchemyUserRepository
from app.infrastructure.repositories.workspace import SqlAlchemyWorkspaceRepository
from app.infrastructure.security.password import BcryptPasswordHasher
from app.infrastructure.security.tokens import JwtSettings, JwtTokenService


def get_settings() -> Settings:
    return settings


@lru_cache(maxsize=1)
def get_password_hasher() -> PasswordHasher:
    return BcryptPasswordHasher()


def get_token_service(
    config: Annotated[Settings, Depends(get_settings)],
) -> TokenService:
    return JwtTokenService(
        JwtSettings(
            secret=config.jwt_secret,
            algorithm=config.jwt_algorithm,
            human_ttl_seconds=config.jwt_human_ttl_seconds,
            agent_ttl_seconds=config.jwt_agent_ttl_seconds,
            issuer=config.jwt_issuer,
        )
    )


SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_member_repository(session: SessionDep) -> MemberRepository:
    return SqlAlchemyMemberRepository(session)


def get_credentials_repository(session: SessionDep) -> CredentialsRepository:
    return SqlAlchemyCredentialsRepository(session)


def get_workspace_repository(session: SessionDep) -> WorkspaceRepository:
    return SqlAlchemyWorkspaceRepository(session)


def get_user_repository(session: SessionDep) -> UserRepository:
    return SqlAlchemyUserRepository(session)


def get_workspace_read_repository(session: SessionDep) -> WorkspaceReadRepository:
    return SqlAlchemyWorkspaceRepository(session)


def get_workspace_write_repository(session: SessionDep) -> WorkspaceWriteRepository:
    # Same SQLAlchemy class — different protocol surface (rename).
    return SqlAlchemyWorkspaceRepository(session)


def get_workspace_service(
    workspaces: Annotated[WorkspaceWriteRepository, Depends(get_workspace_write_repository)],
) -> WorkspaceService:
    return WorkspaceService(workspaces=workspaces)


WorkspaceServiceDep = Annotated[WorkspaceService, Depends(get_workspace_service)]


def get_auth_service(
    workspaces: Annotated[WorkspaceRepository, Depends(get_workspace_repository)],
    members: Annotated[MemberRepository, Depends(get_member_repository)],
    credentials: Annotated[CredentialsRepository, Depends(get_credentials_repository)],
    hasher: Annotated[PasswordHasher, Depends(get_password_hasher)],
    tokens: Annotated[TokenService, Depends(get_token_service)],
    users: Annotated[UserRepository, Depends(get_user_repository)],
) -> AuthService:
    return AuthService(
        workspaces=workspaces,
        members=members,
        credentials=credentials,
        hasher=hasher,
        tokens=tokens,
        users=users,
    )


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


def get_task_repository(session: SessionDep) -> TaskRepository:
    return SqlAlchemyTaskRepository(session)


def get_project_repository(session: SessionDep) -> ProjectRepository:
    return SqlAlchemyProjectRepository(session)


def get_team_repository(session: SessionDep) -> TeamRepository:
    return SqlAlchemyTeamRepository(session)


def get_task_rating_repository(session: SessionDep) -> TaskRatingRepository:
    return SqlAlchemyTaskRatingRepository(session)


def get_task_comment_repository(session: SessionDep) -> TaskCommentRepository:
    return SqlAlchemyTaskCommentRepository(session)


def get_task_relation_repository(session: SessionDep) -> TaskRelationRepository:
    return SqlAlchemyTaskRelationRepository(session)


def get_task_activity_repository(session: SessionDep) -> TaskActivityRepository:
    return SqlAlchemyTaskActivityRepository(session)


def get_task_request_repository(session: SessionDep) -> TaskRequestRepository:
    return SqlAlchemyTaskRequestRepository(session)


def get_workspace_task_seq_repository(session: SessionDep) -> WorkspaceTaskSeqRepository:
    # Same SQLAlchemy class as the auth-side workspace repo; different
    # protocol surface (allocate_next_task_seq).
    return SqlAlchemyWorkspaceRepository(session)


def get_task_service(
    tasks: Annotated[TaskRepository, Depends(get_task_repository)],
    members: Annotated[MemberRepository, Depends(get_member_repository)],
    workspaces: Annotated[WorkspaceReadRepository, Depends(get_workspace_read_repository)],
    seq_allocator: Annotated[
        WorkspaceTaskSeqRepository, Depends(get_workspace_task_seq_repository)
    ],
    ratings: Annotated[TaskRatingRepository, Depends(get_task_rating_repository)],
    comments: Annotated[TaskCommentRepository, Depends(get_task_comment_repository)],
    relations: Annotated[TaskRelationRepository, Depends(get_task_relation_repository)],
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
    team_lookup: Annotated[TeamRepository, Depends(get_team_repository)],
    activities: Annotated[TaskActivityRepository, Depends(get_task_activity_repository)],
    requests: Annotated[TaskRequestRepository, Depends(get_task_request_repository)],
    notifications: Annotated[NotificationService, Depends(get_notification_service)],
) -> TaskService:
    return TaskService(
        tasks=tasks,
        members=members,
        workspaces=workspaces,
        seq_allocator=seq_allocator,
        ratings=ratings,
        comments=comments,
        relations=relations,
        projects=projects,
        team_lookup=team_lookup,
        activities=activities,
        requests=requests,
        notifications=notifications,
    )


TaskServiceDep = Annotated[TaskService, Depends(get_task_service)]


def get_project_service(
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
    tasks: Annotated[TaskRepository, Depends(get_task_repository)],
    activities: Annotated[TaskActivityRepository, Depends(get_task_activity_repository)],
    comments: Annotated[TaskCommentRepository, Depends(get_task_comment_repository)],
    ratings: Annotated[TaskRatingRepository, Depends(get_task_rating_repository)],
    members: Annotated[MemberRepository, Depends(get_member_repository)],
    workspaces: Annotated[WorkspaceReadRepository, Depends(get_workspace_read_repository)],
) -> ProjectService:
    return ProjectService(
        projects=projects,
        tasks=tasks,
        activities=activities,
        comments=comments,
        ratings=ratings,
        members=members,
        workspaces=workspaces,
    )


ProjectServiceDep = Annotated[ProjectService, Depends(get_project_service)]


def get_department_repository(session: SessionDep) -> DepartmentRepository:
    return SqlAlchemyDepartmentRepository(session)


def get_audit_log_repository(session: SessionDep) -> AuditLogRepository:
    return SqlAlchemyAuditLogRepository(session)


def get_audit_log_service(
    audit_logs: Annotated[AuditLogRepository, Depends(get_audit_log_repository)],
    members: Annotated[MemberRepository, Depends(get_member_repository)],
    teams: Annotated[TeamRepository, Depends(get_team_repository)],
) -> AuditLogService:
    return AuditLogService(audit_logs=audit_logs, members=members, teams=teams)


AuditLogServiceDep = Annotated[AuditLogService, Depends(get_audit_log_service)]


def get_department_service(
    departments: Annotated[DepartmentRepository, Depends(get_department_repository)],
    audit_logs: Annotated[AuditLogService, Depends(get_audit_log_service)],
    members: Annotated[MemberRepository, Depends(get_member_repository)],
) -> DepartmentService:
    return DepartmentService(departments=departments, audit_logs=audit_logs, members=members)


DepartmentServiceDep = Annotated[DepartmentService, Depends(get_department_service)]


def get_team_service(
    teams: Annotated[TeamRepository, Depends(get_team_repository)],
    departments: Annotated[DepartmentRepository, Depends(get_department_repository)],
    audit_logs: Annotated[AuditLogService, Depends(get_audit_log_service)],
) -> TeamService:
    return TeamService(teams=teams, departments=departments, audit_logs=audit_logs)


TeamServiceDep = Annotated[TeamService, Depends(get_team_service)]


def get_invite_repository(session: SessionDep) -> InviteRepository:
    return SqlAlchemyInviteRepository(session)


def get_tenant_member_repository(session: SessionDep) -> TenantMemberRepository:
    # Same SQLAlchemy class — different protocol surface (list_for_workspace).
    return SqlAlchemyMemberRepository(session)


def get_invite_service(
    invites: Annotated[InviteRepository, Depends(get_invite_repository)],
    tenant_members: Annotated[TenantMemberRepository, Depends(get_tenant_member_repository)],
    workspaces: Annotated[WorkspaceReadRepository, Depends(get_workspace_read_repository)],
    auth_members: Annotated[MemberRepository, Depends(get_member_repository)],
    credentials: Annotated[CredentialsRepository, Depends(get_credentials_repository)],
    hasher: Annotated[PasswordHasher, Depends(get_password_hasher)],
    tokens: Annotated[TokenService, Depends(get_token_service)],
    config: Annotated[Settings, Depends(get_settings)],
    teams: Annotated[TeamRepository, Depends(get_team_repository)],
    users: Annotated[UserRepository, Depends(get_user_repository)],
    audit_logs: Annotated[AuditLogService, Depends(get_audit_log_service)],
) -> InviteService:
    return InviteService(
        invites=invites,
        members=tenant_members,
        workspaces=workspaces,
        auth_members=auth_members,
        credentials=credentials,
        hasher=hasher,
        tokens=tokens,
        # Invite links resolve on the SaaS app subdomain — same place the
        # frontend serves /invite/[token].
        accept_url_base=config.oauth_post_login_redirect.rsplit("/auth/callback", 1)[0],
        teams=teams,
        users=users,
        audit_logs=audit_logs,
    )


InviteServiceDep = Annotated[InviteService, Depends(get_invite_service)]


def get_agent_member_repository(session: SessionDep) -> AgentMemberRepository:
    # Same SQLAlchemy class — different protocol (list_agents_for_workspace).
    return SqlAlchemyMemberRepository(session)


def get_agent_service(
    members_for_listing: Annotated[AgentMemberRepository, Depends(get_agent_member_repository)],
    auth_members: Annotated[MemberRepository, Depends(get_member_repository)],
    credentials: Annotated[CredentialsRepository, Depends(get_credentials_repository)],
    hasher: Annotated[PasswordHasher, Depends(get_password_hasher)],
) -> AgentService:
    return AgentService(
        members_for_listing=members_for_listing,
        auth_members=auth_members,
        credentials=credentials,
        hasher=hasher,
    )


AgentServiceDep = Annotated[AgentService, Depends(get_agent_service)]


def get_me_member_repository(session: SessionDep) -> MeMemberRepository:
    # Same SQLAlchemy class as the others — distinct protocol surface.
    return SqlAlchemyMemberRepository(session)


def get_notification_repository(session: SessionDep) -> NotificationRepository:
    return SqlAlchemyNotificationRepository(session)


def get_mention_lookup(session: SessionDep) -> MentionMemberLookup:
    # Same SQLAlchemy class as the rest of the member surface; declared
    # under a distinct Protocol so the notifications service depends on
    # only the slice it needs.
    return SqlAlchemyMemberRepository(session)


def get_notification_service(
    notifications: Annotated[NotificationRepository, Depends(get_notification_repository)],
    members: Annotated[MentionMemberLookup, Depends(get_mention_lookup)],
) -> NotificationService:
    return NotificationService(notifications=notifications, members=members)


NotificationServiceDep = Annotated[NotificationService, Depends(get_notification_service)]


def get_me_service(
    users: Annotated[UserRepository, Depends(get_user_repository)],
    members: Annotated[MeMemberRepository, Depends(get_me_member_repository)],
    workspaces: Annotated[WorkspaceRepository, Depends(get_workspace_repository)],
    hasher: Annotated[PasswordHasher, Depends(get_password_hasher)],
    notifications: Annotated[NotificationRepository, Depends(get_notification_repository)],
    tokens: Annotated[TokenService, Depends(get_token_service)],
    tasks: Annotated[TaskRepository, Depends(get_task_repository)],
) -> MeService:
    return MeService(
        users=users,
        members=members,
        workspaces=workspaces,
        hasher=hasher,
        notifications=notifications,
        tokens=tokens,
        tasks=tasks,
    )


_bearer_scheme = HTTPBearer(auto_error=True, description="Bearer JWT issued by /auth")


def _decode_principal(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer_scheme)],
    tokens: Annotated[TokenService, Depends(get_token_service)],
) -> Principal:
    """JWT-only principal builder. Doesn't touch the DB — used inside
    ``get_current_principal`` and inside paths (e.g. selection-token
    exchange) that intentionally bypass the suspension gate."""
    if not isinstance(tokens, JwtTokenService):  # pragma: no cover - DI invariant
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="token service does not support decoding",
        )
    try:
        payload = tokens.decode(credentials.credentials)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    try:
        member_id = UUID(str(payload["sub"]))
        workspace_id = UUID(str(payload["workspace_id"]))
        member_type = MemberType(str(payload["type"]))
        priority = int(str(payload["priority"]))
        scope = str(payload["scope"])
        # `role` was added in migration 0004. Tokens minted before the
        # claim existed default to USER — least-privileged so they
        # can't perform OWNER/ADMIN actions until they re-auth.
        # Migration 0021 also renamed the value WORKSPACE_MEMBER →
        # WORKSPACE_USER. Tokens minted before that migration carry
        # the old string; we map them transparently so existing
        # sessions don't 401 mid-flight after the deploy.
        raw_role = str(payload.get("role", MemberRole.WORKSPACE_USER.value))
        if raw_role == "WORKSPACE_MEMBER":
            raw_role = MemberRole.WORKSPACE_USER.value
        role = MemberRole(raw_role)
    except (KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="malformed token payload",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return Principal(
        member_id=member_id,
        workspace_id=workspace_id,
        type=member_type,
        priority=priority,
        scope=scope,
        role=role,
    )


async def get_current_principal(
    principal: Annotated[Principal, Depends(_decode_principal)],
    members: Annotated[MemberRepository, Depends(get_member_repository)],
) -> Principal:
    """Decode the JWT AND enforce the workspace-scoped suspension lock.

    A suspended member can still hold a valid (non-expired) JWT — the
    gate sits here, in front of every workspace-scoped route, so the
    moment an admin flips ``is_suspended`` on the member row the next
    request bounces with 403. The underlying User row is untouched, so
    the human can still log in and use any *other* workspace they
    belong to: the lock is per-membership, not per-user.

    Tokens with the ``select`` scope (the short-lived
    multi-workspace-picker token) are not workspace-bound — they don't
    target a specific member, so this check is skipped. Workspace
    binding happens on the subsequent ``select_workspace`` call, which
    re-issues a fresh JWT.

    A 401 is returned (not 403) when the member row no longer exists
    so a freshly deleted member can't keep using their old token.
    """
    if principal.scope == "select":
        return principal

    member = await members.get_by_id(principal.member_id)
    if member is None or member.workspace_id != principal.workspace_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if member.is_suspended:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="your access to this workspace has been suspended",
        )
    return principal


PrincipalDep = Annotated[Principal, Depends(get_current_principal)]


# Variant that skips the suspension check. Reserved for the few
# endpoints that a suspended user must still be able to reach — e.g.
# /auth/switch-workspace, where the whole point is to escape the
# suspended workspace into one the user still has access to. Do NOT
# apply this anywhere else — every other route MUST go through the
# suspension gate.
RawPrincipalDep = Annotated[Principal, Depends(_decode_principal)]


def require_workspace_admin(principal: PrincipalDep) -> Principal:
    """RBAC guard: rejects MEMBER and AGENT principals on routes that only
    workspace owners/admins should hit (invites, team management)."""
    if principal.role not in (MemberRole.WORKSPACE_OWNER, MemberRole.WORKSPACE_ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="workspace owner or admin role required",
        )
    return principal


WorkspaceAdminDep = Annotated[Principal, Depends(require_workspace_admin)]


def require_admin_priority_le(max_priority: int):
    """RBAC factory dep — admin role *and* priority ≤ ``max_priority``.

    The Phase-6 RBAC matrix gates an admin's *reach* on top of their
    role: a Priority-2 Admin can manage Departments, a Priority-3
    Admin only Teams, etc. Owners always pass (their priority is 1
    and they're conceptually above the admin tier).

    Usage in a router:

        from app.api.deps import require_admin_priority_le
        DepartmentReachDep = Annotated[
            Principal, Depends(require_admin_priority_le(2))
        ]

    Returns a sync dep function (not an Annotated type) so the same
    factory can produce gates at different priority thresholds. Wrap
    in ``Annotated[Principal, Depends(...)]`` at the call-site, or
    expose pre-built ``DepartmentReachDep`` / ``TeamReachDep``
    aliases (see below).
    """

    def _dep(principal: PrincipalDep) -> Principal:
        if principal.role not in (MemberRole.WORKSPACE_OWNER, MemberRole.WORKSPACE_ADMIN):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="workspace owner or admin role required",
            )
        # Owners are always above the priority bar by convention —
        # they're priority 1 by default, but even a re-prioritised
        # owner shouldn't lose reach over their own workspace.
        if principal.role is MemberRole.WORKSPACE_OWNER:
            return principal
        if principal.priority > max_priority:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"this action requires an admin with priority ≤ {max_priority} "
                    f"(your priority is {principal.priority})"
                ),
            )
        return principal

    return _dep


# Pre-built reach gates for the two layers the spec calls out
# explicitly. Department CRUD requires priority ≤ 2; Team CRUD
# requires priority ≤ 3.
DepartmentReachDep = Annotated[Principal, Depends(require_admin_priority_le(2))]
TeamReachDep = Annotated[Principal, Depends(require_admin_priority_le(3))]


def require_agent_scope(principal: PrincipalDep) -> Principal:
    """Routes that only an agent's own JWT may hit (e.g. self-heartbeat).
    Humans get 403 — they shouldn't be able to spoof an agent's
    presence signal. Agent JWTs carry scope='agent'."""
    if principal.scope != "agent" or principal.type is not MemberType.AGENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="agent scope required",
        )
    return principal


AgentScopeDep = Annotated[Principal, Depends(require_agent_scope)]


def get_oauth_client(provider: OAuthProvider, config: Settings) -> OAuthClient:
    """Build an OAuth client for the requested provider.

    Returns None-equivalent (raises HTTPException) when the corresponding
    env vars aren't set — keeps the api boot-able even if only one of the
    two providers is configured (e.g. GitHub-only local dev).
    """
    if provider is OAuthProvider.GOOGLE:
        if not config.google_oauth_client_id or not config.google_oauth_client_secret:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="google oauth is not configured on this environment",
            )
        return GoogleOAuthClient(
            client_id=config.google_oauth_client_id,
            client_secret=config.google_oauth_client_secret,
        )
    if provider is OAuthProvider.GITHUB:
        if not config.github_oauth_client_id or not config.github_oauth_client_secret:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="github oauth is not configured on this environment",
            )
        return GitHubOAuthClient(
            client_id=config.github_oauth_client_id,
            client_secret=config.github_oauth_client_secret,
        )
    raise HTTPException(  # pragma: no cover - exhaustive enum
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"unsupported oauth provider: {provider}",
    )
