from __future__ import annotations

from functools import lru_cache
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

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
    WorkspaceRepository,
)
from app.application.auth.service import AuthService
from app.application.tasks.ports import TaskRepository
from app.application.tasks.schemas import Principal
from app.application.tasks.service import TaskService
from app.application.tenants.ports import (
    InviteRepository,
    TenantMemberRepository,
    WorkspaceReadRepository,
)
from app.application.tenants.service import InviteService
from app.core.config import Settings, settings
from app.domain.enums import MemberRole, MemberType, OAuthProvider
from app.infrastructure.db.session import get_session
from app.infrastructure.repositories.credentials import SqlAlchemyCredentialsRepository
from app.infrastructure.repositories.invite import SqlAlchemyInviteRepository
from app.infrastructure.repositories.member import SqlAlchemyMemberRepository
from app.infrastructure.repositories.task import SqlAlchemyTaskRepository
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


def get_auth_service(
    workspaces: Annotated[WorkspaceRepository, Depends(get_workspace_repository)],
    members: Annotated[MemberRepository, Depends(get_member_repository)],
    credentials: Annotated[CredentialsRepository, Depends(get_credentials_repository)],
    hasher: Annotated[PasswordHasher, Depends(get_password_hasher)],
    tokens: Annotated[TokenService, Depends(get_token_service)],
) -> AuthService:
    return AuthService(
        workspaces=workspaces,
        members=members,
        credentials=credentials,
        hasher=hasher,
        tokens=tokens,
    )


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


def get_task_repository(session: SessionDep) -> TaskRepository:
    return SqlAlchemyTaskRepository(session)


def get_task_service(
    tasks: Annotated[TaskRepository, Depends(get_task_repository)],
    members: Annotated[MemberRepository, Depends(get_member_repository)],
) -> TaskService:
    return TaskService(tasks=tasks, members=members)


TaskServiceDep = Annotated[TaskService, Depends(get_task_service)]


def get_invite_repository(session: SessionDep) -> InviteRepository:
    return SqlAlchemyInviteRepository(session)


def get_tenant_member_repository(session: SessionDep) -> TenantMemberRepository:
    # Same SQLAlchemy class — different protocol surface (list_for_workspace).
    return SqlAlchemyMemberRepository(session)


def get_workspace_read_repository(session: SessionDep) -> WorkspaceReadRepository:
    return SqlAlchemyWorkspaceRepository(session)


def get_invite_service(
    invites: Annotated[InviteRepository, Depends(get_invite_repository)],
    tenant_members: Annotated[TenantMemberRepository, Depends(get_tenant_member_repository)],
    workspaces: Annotated[WorkspaceReadRepository, Depends(get_workspace_read_repository)],
    auth_members: Annotated[MemberRepository, Depends(get_member_repository)],
    credentials: Annotated[CredentialsRepository, Depends(get_credentials_repository)],
    hasher: Annotated[PasswordHasher, Depends(get_password_hasher)],
    tokens: Annotated[TokenService, Depends(get_token_service)],
    config: Annotated[Settings, Depends(get_settings)],
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
    )


InviteServiceDep = Annotated[InviteService, Depends(get_invite_service)]


_bearer_scheme = HTTPBearer(auto_error=True, description="Bearer JWT issued by /auth")


def get_current_principal(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer_scheme)],
    tokens: Annotated[TokenService, Depends(get_token_service)],
) -> Principal:
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
        # claim existed default to MEMBER — least-privileged so they
        # can't perform OWNER/ADMIN actions until they re-auth.
        role = MemberRole(str(payload.get("role", MemberRole.MEMBER.value)))
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


PrincipalDep = Annotated[Principal, Depends(get_current_principal)]


def require_workspace_admin(principal: PrincipalDep) -> Principal:
    """RBAC guard: rejects MEMBER and AGENT principals on routes that only
    workspace owners/admins should hit (invites, team management)."""
    if principal.role not in (MemberRole.OWNER, MemberRole.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="workspace owner or admin role required",
        )
    return principal


WorkspaceAdminDep = Annotated[Principal, Depends(require_workspace_admin)]


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
