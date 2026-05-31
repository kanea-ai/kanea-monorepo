from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

import jwt
from sqlalchemy.exc import IntegrityError

from app.application.agents.api_key_ports import AgentApiKeyRepository
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
    SwitchWorkspaceRequest,
    TokenResponse,
    WorkspaceOption,
)
from app.application.tasks.schemas import Principal
from app.domain.entities import Member, User, Workspace
from app.domain.enums import MemberRole, MemberType
from app.domain.exceptions import (
    AuthenticationError,
    EmailAlreadyExistsError,
    WorkspaceNameConflictError,
)
from app.infrastructure.security.agent_api_keys import parse_and_hash

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
    agent_api_keys: AgentApiKeyRepository
    agent_api_key_env_tag: str
    agent_api_key_pepper: str
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

    async def switch_workspace(
        self, requester: Principal, request: SwitchWorkspaceRequest
    ) -> TokenResponse:
        """Reissue the access token bound to a different workspace the
        same user belongs to. The principal already authenticates the
        user — we just verify the target membership exists and mint a
        fresh token. Distinct from select_workspace because we don't
        need a selection_token here; the bearer JWT already proves who
        is asking."""
        # Resolve the calling user via their current member.
        current = await self.members.get_by_id(requester.member_id)
        if current is None or current.user_id is None:
            raise AuthenticationError("member not found")

        memberships = await self.members.list_for_user(current.user_id)
        match = next(
            (m for m in memberships if m.workspace_id == request.workspace_id),
            None,
        )
        if match is None or match.type is not MemberType.HUMAN:
            raise AuthenticationError("you don't have access to this workspace")

        token, ttl = self.tokens.issue_human_token(match)
        return TokenResponse(access_token=token, expires_in=ttl)

    async def issue_agent_token(self, request: AgentTokenRequest) -> TokenResponse:
        """Exchange a ``kna_<env>_<body>`` API key for a scope='agent' JWT.

        Path: parse the prefix + env-tag → HMAC the body → SELECT the
        active row in ``agent_api_keys`` → load the agent → mint the
        JWT → stamp ``last_used_at`` on the key AND ``last_seen_at``
        on the member in the same transaction.

        Every step returns the same generic ``invalid agent credentials``
        error on failure so an attacker can't tell whether the key was
        malformed, wrong env, unknown, revoked, or pointed at a deleted
        agent.
        """
        secret_hash = parse_and_hash(
            request.api_key,
            expected_env_tag=self.agent_api_key_env_tag,
            pepper=self.agent_api_key_pepper,
        )
        if secret_hash is None:
            raise AuthenticationError("invalid agent credentials")

        key_row = await self.agent_api_keys.find_active_by_secret_hash(secret_hash)
        if key_row is None:
            raise AuthenticationError("invalid agent credentials")

        member = await self.members.get_by_id(key_row.member_id)
        if member is None or member.type is not MemberType.AGENT:
            raise AuthenticationError("invalid agent credentials")

        now = datetime.utcnow()
        # Last-used stamp on the key + free heartbeat on the member.
        # Persisted in the same transaction as the JWT issuance so the
        # two timestamps can't drift.
        await self.agent_api_keys.mark_used(key_row.id, used_at=now)
        await self.members.heartbeat(member.id)

        token, ttl = self.tokens.issue_agent_token(member)
        return TokenResponse(access_token=token, expires_in=ttl)

    async def oauth_login(self, identity: OAuthIdentity) -> LoginResponse:
        """Resolve an OAuth identity to one of three shapes.

        Resolution order:
          1) (provider, oauth_id) already known on a User — log in.
          2) Same email exists on a User — link the OAuth identity
             and log in.
          3) Brand new — mint an *onboarding* token carrying the
             OAuth identity and return ``requires_onboarding=True``.
             No DB rows are created here; the second leg
             (``complete_oauth_onboarding``) actually provisions the
             User + Workspace + Member with the workspace name the
             user picked on the ``/onboarding/workspace`` screen.

        Why defer? Auto-naming the workspace ``"{full_name}'s
        workspace"`` was a usability tax on SSO signups — operators
        almost always want to pick a real brand name. Deferring to
        an explicit prompt also means no orphan User row sits in the
        DB if a user abandons signup at the redirect step.
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
                # Brand new SSO user — defer provisioning to
                # complete_oauth_onboarding. The onboarding token is
                # the only state we keep until the user picks a name.
                onboarding_token, ttl = self.tokens.issue_onboarding_token(identity)
                return LoginResponse(
                    requires_onboarding=True,
                    onboarding_token=onboarding_token,
                    expires_in=ttl,
                    suggested_workspace_name=_default_workspace_name(identity.name),
                )

        return await self._login_existing_user(user)

    async def complete_oauth_onboarding(
        self, *, onboarding_token: str, workspace_name: str
    ) -> TokenResponse:
        """Second leg of the SSO signup flow. Decodes the onboarding
        token to recover the OAuth identity, then provisions the
        User + Workspace + Member trio with the caller-supplied
        workspace name.

        Race-safety: a parallel tab may have already finished the
        signup (rare but possible). We check for an existing
        ``(provider, oauth_id)`` on a User first and short-circuit
        to a normal login if it exists — no double-provision."""
        if self.users is None:  # pragma: no cover - DI invariant
            raise RuntimeError("users repo not wired")

        try:
            identity = self.tokens.decode_onboarding_token(onboarding_token)
        except jwt.PyJWTError as exc:
            raise AuthenticationError("invalid or expired onboarding token") from exc

        # Race: another tab already finished. Fall through to the
        # normal login path so the caller gets a working token
        # without us tripping the IntegrityError on the duplicate
        # OAuth identity.
        existing = await self.users.get_by_oauth_identity(identity.provider, identity.oauth_id)
        if existing is not None:
            return await self._login_existing_user(existing)

        now = datetime.utcnow()
        user = await self.users.create(
            User(
                id=uuid4(),
                email=identity.email,
                full_name=identity.name or identity.email,
                oauth_provider=identity.provider,
                oauth_id=identity.oauth_id,
            )
        )
        try:
            workspace = await self.workspaces.create(
                Workspace(
                    id=uuid4(),
                    name=workspace_name,
                    slug=_generate_slug(workspace_name),
                    task_prefix=_generate_task_prefix(workspace_name),
                    next_task_seq=1,
                    created_at=now,
                    updated_at=now,
                )
            )
        except IntegrityError as exc:
            # workspaces.name UNIQUE (migration 0016) — surface as
            # 409 to the route. The User row created above is OK to
            # leave: a follow-up complete_oauth_onboarding with a
            # different name will take the race-safety path and reuse
            # the existing User.
            raise WorkspaceNameConflictError("a workspace with that name already exists") from exc

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

        # Brand-new path always lands as a single-membership user.
        # We reuse the existing-user branching to keep the multi-vs-
        # single membership logic in one place; the response is
        # always a TokenResponse for this caller because the user
        # was just created with exactly one Member row.
        resolved = await self._login_existing_user(user)
        # Defensive — the user-was-just-created invariant means this
        # is always the access_token branch, but if somehow it isn't
        # we'd rather raise than silently return a selection token
        # from an endpoint typed as TokenResponse.
        if resolved.access_token is None or resolved.expires_in is None:
            raise AuthenticationError(
                "onboarding completion produced an unexpected multi-membership state"
            )
        return TokenResponse(access_token=resolved.access_token, expires_in=resolved.expires_in)

    async def _login_existing_user(self, user: User) -> LoginResponse:
        """Resolve a user's memberships into a LoginResponse. Single
        membership → access_token; multi-membership → selection_token
        + workspaces list (same shape password login produces)."""
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


# Slugs are unique per workspace and we always append a 6-hex-char suffix
# so signups never collide on the slug column. Trades a little prettiness
# for never having to retry on conflict.
_SLUG_NORMALIZE = re.compile(r"[^a-z0-9]+")
_PREFIX_NORMALIZE = re.compile(r"[^A-Z]")


def _generate_slug(name: str) -> str:
    base = _SLUG_NORMALIZE.sub("-", name.lower()).strip("-")[:48] or "workspace"
    suffix = secrets.token_hex(3)
    return f"{base}-{suffix}"


def _default_workspace_name(full_name: str | None) -> str:
    """Suggested workspace name shown on the onboarding screen as a
    placeholder. Mirrors the old auto-naming template so existing
    users who scroll past without changing it get the same name they
    would have before — but it's now an explicit choice."""
    return f"{full_name}'s workspace" if full_name else "Workspace"


def _generate_task_prefix(name: str) -> str:
    """Derive a short alpha prefix for human-readable task ids.

    Strips non-alpha, uppercases, takes first 6 chars. Falls back to
    ``TASK`` if the name has no alpha content. Editable later via a
    workspace-settings endpoint we haven't built yet."""
    cleaned = _PREFIX_NORMALIZE.sub("", name.upper())
    return cleaned[:6] if cleaned else "TASK"
