from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from app.application.agents.ports import AgentMemberRepository
from app.application.agents.schemas import (
    AgentResponse,
    CreateAgentRequest,
    CreateAgentResponse,
)
from app.application.auth.ports import (
    CredentialsRepository,
    MemberRepository,
    PasswordHasher,
)
from app.application.tasks.schemas import Principal
from app.domain.entities import Credentials, Member
from app.domain.enums import MemberRole, MemberType


@dataclass(slots=True)
class AgentService:
    members_for_listing: AgentMemberRepository
    auth_members: MemberRepository
    credentials: CredentialsRepository
    hasher: PasswordHasher

    async def create_agent(
        self, request: CreateAgentRequest, principal: Principal
    ) -> CreateAgentResponse:
        """Provision a new AGENT-typed member in the requester's workspace
        with a freshly-minted API key. Key is shown to the caller exactly
        once — we bcrypt-hash it on persist and can't recover the
        plaintext. The agent later exchanges (id, key) at
        POST /api/v1/auth/agent-token for a short-lived JWT."""
        api_key = secrets.token_urlsafe(32)  # 256 bits of entropy

        now = datetime.utcnow()
        member = await self.auth_members.create(
            Member(
                id=uuid4(),
                workspace_id=principal.workspace_id,
                type=MemberType.AGENT,
                name=request.name,
                # Agents don't get a workspace email; identity is via the
                # API key alone.
                email=None,
                priority=request.priority,
                role=MemberRole.MEMBER,
                created_at=now,
                updated_at=now,
            )
        )
        await self.credentials.create(
            Credentials(
                id=uuid4(),
                member_id=member.id,
                password_hash=None,
                agent_secret_hash=self.hasher.hash(api_key),
                created_at=now,
                updated_at=now,
            )
        )

        return CreateAgentResponse(
            id=member.id,
            workspace_id=member.workspace_id,
            name=member.name,
            priority=member.priority,
            api_key=api_key,
        )

    async def list_agents(self, principal: Principal) -> list[AgentResponse]:
        agents = await self.members_for_listing.list_agents_for_workspace(principal.workspace_id)
        return [AgentResponse.from_entity(a) for a in agents]
