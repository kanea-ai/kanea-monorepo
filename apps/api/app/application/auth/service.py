from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from app.application.auth.oauth import OAuthIdentity
from app.application.auth.ports import (
    CredentialsRepository,
    MemberRepository,
    PasswordHasher,
    TokenService,
    WorkspaceRepository,
)
from app.application.auth.schemas import (
    AgentTokenRequest,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
)
from app.domain.entities import Credentials, Member, Workspace
from app.domain.enums import MemberType
from app.domain.exceptions import AuthenticationError, EmailAlreadyExistsError

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

    async def register(self, request: RegisterRequest) -> TokenResponse:
        # We don't enforce a *global* unique email — the DB constraint is
        # per-workspace. But on signup the workspace is brand-new, so the
        # only way to collide is if the same address tries to sign up
        # twice in the same race; that surfaces as IntegrityError and is
        # surfaced to the caller.
        existing = await self.members.get_by_email(str(request.email))
        if existing is not None:
            raise EmailAlreadyExistsError("an account with this email already exists")

        workspace = await self.workspaces.create(
            Workspace(
                id=uuid4(),
                name=request.workspace_name,
                slug=_generate_slug(request.workspace_name),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        )

        member = await self.members.create(
            Member(
                id=uuid4(),
                workspace_id=workspace.id,
                type=MemberType.HUMAN,
                name=request.full_name,
                email=str(request.email),
                priority=OWNER_PRIORITY,
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

        token, ttl = self.tokens.issue_human_token(member)
        return TokenResponse(access_token=token, expires_in=ttl)

    async def login(self, request: LoginRequest) -> TokenResponse:
        member = await self.members.get_by_email(str(request.email))
        if member is None or member.type is not MemberType.HUMAN:
            raise AuthenticationError("invalid email or password")

        creds = await self.credentials.get_for_member(member.id)
        if creds is None or creds.password_hash is None:
            raise AuthenticationError("invalid email or password")

        if not self.hasher.verify(request.password, creds.password_hash):
            raise AuthenticationError("invalid email or password")

        token, ttl = self.tokens.issue_human_token(member)
        return TokenResponse(access_token=token, expires_in=ttl)

    async def issue_agent_token(self, request: AgentTokenRequest) -> TokenResponse:
        member = await self._load_agent(request.agent_id)

        creds = await self.credentials.get_for_member(member.id)
        if creds is None or creds.agent_secret_hash is None:
            raise AuthenticationError("invalid agent credentials")

        if not self.hasher.verify(request.secret, creds.agent_secret_hash):
            raise AuthenticationError("invalid agent credentials")

        token, ttl = self.tokens.issue_agent_token(member)
        return TokenResponse(access_token=token, expires_in=ttl)

    async def oauth_login(self, identity: OAuthIdentity) -> TokenResponse:
        """Resolve an OAuth identity to a JWT.

        Resolution order:
          1) (provider, oauth_id) already known -> log that member in.
          2) Same email exists on a member -> link the OAuth identity to
             that member's credentials and log them in.
          3) Brand new -> provision a Workspace + HUMAN Member (priority=1,
             owner) + Credentials carrying the OAuth identity, no password.
        """
        existing_oauth_creds = await self.credentials.get_by_oauth_identity(
            identity.provider.value, identity.oauth_id
        )
        if existing_oauth_creds is not None:
            member = await self.members.get_by_id(existing_oauth_creds.member_id)
            if member is None:  # pragma: no cover - DB invariant
                raise AuthenticationError("dangling oauth credentials")
            token, ttl = self.tokens.issue_human_token(member)
            return TokenResponse(access_token=token, expires_in=ttl)

        existing_member = await self.members.get_by_email(identity.email)
        if existing_member is not None:
            if existing_member.type is not MemberType.HUMAN:
                raise AuthenticationError("email is registered to a non-human member")
            await self.credentials.link_oauth_identity(
                existing_member.id, identity.provider.value, identity.oauth_id
            )
            token, ttl = self.tokens.issue_human_token(existing_member)
            return TokenResponse(access_token=token, expires_in=ttl)

        # First-time signup via OAuth — auto-provision a workspace.
        workspace = await self.workspaces.create(
            Workspace(
                id=uuid4(),
                name=f"{identity.name}'s workspace" if identity.name else "Workspace",
                slug=_generate_slug(identity.name or "workspace"),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        )
        member = await self.members.create(
            Member(
                id=uuid4(),
                workspace_id=workspace.id,
                type=MemberType.HUMAN,
                name=identity.name or identity.email,
                email=identity.email,
                priority=OWNER_PRIORITY,
            )
        )
        await self.credentials.create(
            Credentials(
                id=uuid4(),
                member_id=member.id,
                password_hash=None,
                agent_secret_hash=None,
                oauth_provider=identity.provider,
                oauth_id=identity.oauth_id,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        )
        token, ttl = self.tokens.issue_human_token(member)
        return TokenResponse(access_token=token, expires_in=ttl)

    async def _load_agent(self, agent_id: UUID) -> Member:
        member = await self.members.get_by_id(agent_id)
        if member is None or member.type is not MemberType.AGENT:
            raise AuthenticationError("invalid agent credentials")
        return member


# Slugs are unique per workspace and we always append a 6-hex-char suffix
# so signups never collide on the slug column. Trades a little prettiness
# for never having to retry on conflict.
_SLUG_NORMALIZE = re.compile(r"[^a-z0-9]+")


def _generate_slug(name: str) -> str:
    base = _SLUG_NORMALIZE.sub("-", name.lower()).strip("-")[:48] or "workspace"
    suffix = secrets.token_hex(3)
    return f"{base}-{suffix}"
