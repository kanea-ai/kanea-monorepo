from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.application.auth.ports import (
    CredentialsRepository,
    MemberRepository,
    PasswordHasher,
    TokenService,
)
from app.application.auth.schemas import AgentTokenRequest, LoginRequest, TokenResponse
from app.domain.entities import Member
from app.domain.enums import MemberType
from app.domain.exceptions import AuthenticationError


@dataclass(slots=True)
class AuthService:
    members: MemberRepository
    credentials: CredentialsRepository
    hasher: PasswordHasher
    tokens: TokenService

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

    async def _load_agent(self, agent_id: UUID) -> Member:
        member = await self.members.get_by_id(agent_id)
        if member is None or member.type is not MemberType.AGENT:
            raise AuthenticationError("invalid agent credentials")
        return member
