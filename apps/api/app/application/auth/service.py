from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

import jwt
from sqlalchemy.exc import IntegrityError

from app.application.auth.oauth import OAuthIdentity
from app.application.auth.ports import (
    CredentialsRepository,
    MemberRepository,
    PasswordHasher,
    TokenService,
    UserRepository,
    WorkspaceRepository,
)
from app.application.auth.schemas import (
    AgentTokenRequest,
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    SelectWorkspaceRequest,
    TokenResponse,
    WorkspaceOption,
)
from app.domain.entities import Member, User, Workspace
from app.domain.enums import MemberRole, MemberType
from app.domain.exceptions import (
    AuthenticationError,
    EmailAlreadyExistsError,
    WorkspaceNameConflictError,
)

# Workspace owners are the highest rank in the hierarchy. The delegate
# rule (lower number = higher priority) keys off this.
OWNER_PRIORITY = 1


@dataclass(slots=True)
class AuthService:
    workspaces: WorkspaceRepository
    members: MemberRepository
    credentials: CredentialsRepository
    hasher: PasswordHasher
    tokens: TokenService
    # Phase 1 multi-tenancy: human auth lives on the global User row.
    # Optional so legacy DI / unit-test constructors stay compatible —
    # the login + register paths raise if it's missing.
    users: UserRepository | None = None

    async def register(self, request: RegisterRequest) -> TokenResponse:
        if self.users is None:  # pragma: no cover - DI invariant
            raise RuntimeError("users repo not wired")

        # Global email uniqueness now sits on `users`. The user
        # creation will IntegrityError if someone else holds the email,
        # but we surface a clean error pre-emptively.
        existing_user = await self.users.get_by_email(str(request.email))
        if existing_user is not None:
            raise EmailAlreadyExistsError("an account with this email already exists")

        user = await self.users.create(
            User(
                id=uuid4(),
                email=str(request.email),
                full_name=request.full_name,
                password_hash=self.hasher.hash(request.password),
            )
        )

        try:
            workspace = await self.workspaces.create(
                Workspace(
                    id=uuid4(),
                    name=request.workspace_name,
                    slug=_generate_slug(request.workspace_name),
                    task_prefix=_generate_task_prefix(request.workspace_name),
                    next_task_seq=1,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
            )
        except IntegrityError as exc:
            raise WorkspaceNameConflictError(
                f"a workspace named {request.workspace_name!r} already exists"
            ) from exc

        member = await self.members.create(
            Member(
                id=uuid4(),
                workspace_id=workspace.id,
                user_id=user.id,
                type=MemberType.HUMAN,
                name=request.full_name,
                email=str(request.email),
                priority=OWNER_PRIORITY,
                role=MemberRole.WORKSPACE_OWNER,
            )
        )

        token, ttl = self.tokens.issue_human_token(member)
        return TokenResponse(access_token=token, expires_in=ttl)

    async def login(self, request: LoginRequest) -> LoginResponse:
        """Multi-tenancy aware login.

        - Verify password against the global `users` row.
        - Look up all memberships.
        - 0 memberships: 401 (a stranded user — shouldn't happen in
          steady state but guards against orphaned data).
        - 1 membership: emit a normal access token immediately.
        - >1 memberships: emit a short-lived selection token and the
          list of workspaces; UI prompts the user to pick one.
        """
        if self.users is None:  # pragma: no cover - DI invariant
            raise RuntimeError("users repo not wired")

        user = await self.users.get_by_email(str(request.email))
        if user is None or user.password_hash is None:
            raise AuthenticationError("invalid email or password")
        if not self.hasher.verify(request.password, user.password_hash):
            raise AuthenticationError("invalid email or password")

        memberships = await self.members.list_for_user(user.id)
        # Filter to HUMAN memberships defensively — an AGENT row
        # shouldn't ever carry a user_id, but the CHECK constraint is
        # the belt and this is the braces.
        memberships = [m for m in memberships if m.type is MemberType.HUMAN]
        if not memberships:
            raise AuthenticationError("invalid email or password")

        if len(memberships) == 1:
            token, ttl = self.tokens.issue_human_token(memberships[0])
            return LoginResponse(requires_selection=False, access_token=token, expires_in=ttl)

        selection_token, _ttl = self.tokens.issue_selection_token(user)
        options = []
        for m in memberships:
            ws = await self.workspaces.get_by_id(m.workspace_id)
            if ws is None:  # pragma: no cover - FK invariant
                continue
            options.append(
                WorkspaceOption(
                    workspace_id=m.workspace_id,
                    name=ws.name,
                    role=m.role.value,
                )
            )
        return LoginResponse(
            requires_selection=True,
            selection_token=selection_token,
            workspaces=options,
        )

    async def select_workspace(self, request: SelectWorkspaceRequest) -> TokenResponse:
        """Exchange (selection_token, workspace_id) → final access
        token. The token is verified, the workspace must be one of the
        user's memberships."""
        if self.users is None:  # pragma: no cover - DI invariant
            raise RuntimeError("users repo not wired")
        try:
            user_id = self.tokens.decode_selection_token(request.selection_token)
        except jwt.PyJWTError as exc:
            raise AuthenticationError("invalid or expired selection token") from exc

        memberships = await self.members.list_for_user(user_id)
        match = next(
            (m for m in memberships if m.workspace_id == request.workspace_id),
            None,
        )
        if match is None or match.type is not MemberType.HUMAN:
            raise AuthenticationError("no membership for this workspace under that selection token")
        token, ttl = self.tokens.issue_human_token(match)
        return TokenResponse(access_token=token, expires_in=ttl)

    async def issue_agent_token(self, request: AgentTokenRequest) -> TokenResponse:
        member = await self._load_agent(request.agent_id)

        creds = await self.credentials.get_for_member(member.id)
        if creds is None or creds.agent_secret_hash is None:
            raise AuthenticationError("invalid agent credentials")

        if not self.hasher.verify(request.secret, creds.agent_secret_hash):
            raise AuthenticationError("invalid agent credentials")

        # Free presence signal: every successful key-exchange is a
        # heartbeat. Agents that never call the explicit /me/heartbeat
        # still surface as ONLINE for their JWT TTL window.
        await self.members.heartbeat(member.id)

        token, ttl = self.tokens.issue_agent_token(member)
        return TokenResponse(access_token=token, expires_in=ttl)

    async def oauth_login(self, identity: OAuthIdentity) -> LoginResponse:
        """Resolve an OAuth identity to either a token or a selection
        prompt — same shape as password login.

        Resolution order:
          1) (provider, oauth_id) already known on a User — log in.
          2) Same email exists on a User — link the OAuth identity.
          3) Brand new — provision a User + Workspace + Member.
        """
        if self.users is None:  # pragma: no cover - DI invariant
            raise RuntimeError("users repo not wired")

        user = await self.users.get_by_oauth_identity(identity.provider, identity.oauth_id)
        if user is None:
            existing_by_email = await self.users.get_by_email(identity.email)
            if existing_by_email is not None:
                user = await self.users.link_oauth_identity(
                    existing_by_email.id,
                    provider=identity.provider,
                    oauth_id=identity.oauth_id,
                )
            else:
                # First-time signup via OAuth — auto-provision a workspace.
                user = await self.users.create(
                    User(
                        id=uuid4(),
                        email=identity.email,
                        full_name=identity.name or identity.email,
                        oauth_provider=identity.provider,
                        oauth_id=identity.oauth_id,
                    )
                )
                ws_name = f"{identity.name}'s workspace" if identity.name else "Workspace"
                workspace = await self.workspaces.create(
                    Workspace(
                        id=uuid4(),
                        name=ws_name,
                        slug=_generate_slug(identity.name or "workspace"),
                        task_prefix=_generate_task_prefix(identity.name or "workspace"),
                        next_task_seq=1,
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                    )
                )
                await self.members.create(
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

        memberships = await self.members.list_for_user(user.id)
        memberships = [m for m in memberships if m.type is MemberType.HUMAN]
        if not memberships:
            raise AuthenticationError("user has no workspace memberships")

        if len(memberships) == 1:
            token, ttl = self.tokens.issue_human_token(memberships[0])
            return LoginResponse(requires_selection=False, access_token=token, expires_in=ttl)
        selection_token, _ttl = self.tokens.issue_selection_token(user)
        options: list[WorkspaceOption] = []
        for m in memberships:
            ws = await self.workspaces.get_by_id(m.workspace_id)
            if ws is None:  # pragma: no cover
                continue
            options.append(
                WorkspaceOption(workspace_id=m.workspace_id, name=ws.name, role=m.role.value)
            )
        return LoginResponse(
            requires_selection=True,
            selection_token=selection_token,
            workspaces=options,
        )

    async def _load_agent(self, agent_id: UUID) -> Member:
        member = await self.members.get_by_id(agent_id)
        if member is None or member.type is not MemberType.AGENT:
            raise AuthenticationError("invalid agent credentials")
        return member


# Slugs are unique per workspace and we always append a 6-hex-char suffix
# so signups never collide on the slug column. Trades a little prettiness
# for never having to retry on conflict.
_SLUG_NORMALIZE = re.compile(r"[^a-z0-9]+")
_PREFIX_NORMALIZE = re.compile(r"[^A-Z]")


def _generate_slug(name: str) -> str:
    base = _SLUG_NORMALIZE.sub("-", name.lower()).strip("-")[:48] or "workspace"
    suffix = secrets.token_hex(3)
    return f"{base}-{suffix}"


def _generate_task_prefix(name: str) -> str:
    """Derive a short alpha prefix for human-readable task ids.

    Strips non-alpha, uppercases, takes first 6 chars. Falls back to
    ``TASK`` if the name has no alpha content. Editable later via a
    workspace-settings endpoint we haven't built yet."""
    cleaned = _PREFIX_NORMALIZE.sub("", name.upper())
    return cleaned[:6] if cleaned else "TASK"
