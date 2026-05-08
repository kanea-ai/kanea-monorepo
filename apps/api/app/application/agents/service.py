from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from app.application.agents.ports import AgentMemberRepository
from app.application.agents.schemas import (
    AgentDetailResponse,
    AgentResponse,
    AgentStatsResponse,
    CreateAgentRequest,
    CreateAgentResponse,
    UpdateAgentRequest,
)
from app.application.auth.ports import (
    CredentialsRepository,
    MemberRepository,
    PasswordHasher,
)
from app.application.tasks.schemas import Principal
from app.domain.entities import Credentials, Member
from app.domain.enums import MemberRole, MemberType
from app.domain.exceptions import (
    AgentHasCreatedTasksError,
    AgentNotFoundError,
)


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
                model=request.model,
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
            model=member.model,
            api_key=api_key,
        )

    async def list_agents(self, principal: Principal) -> list[AgentResponse]:
        agents = await self.members_for_listing.list_agents_for_workspace(principal.workspace_id)
        return [AgentResponse.from_entity(a) for a in agents]

    async def get_agent_detail(self, agent_id: UUID, principal: Principal) -> AgentDetailResponse:
        """Bundles the agent's safe fields with computed stats. Tenant
        isolation: 404 if the agent isn't in the requester's workspace,
        same shape as truly-missing so cross-tenant probing reveals
        nothing."""
        agent = await self._load_workspace_agent(agent_id, principal)
        stats = await self.members_for_listing.compute_agent_stats(agent.id)
        return AgentDetailResponse(
            id=agent.id,
            workspace_id=agent.workspace_id,
            name=agent.name,
            priority=agent.priority,
            model=agent.model,
            created_at=agent.created_at,
            stats=AgentStatsResponse.from_entity(stats),
        )

    async def update_agent(
        self, agent_id: UUID, request: UpdateAgentRequest, principal: Principal
    ) -> AgentResponse:
        """Partial update of name/priority/model. id stays immutable; an
        empty body is a 200 no-op (Pydantic happily accepts {})."""
        await self._load_workspace_agent(agent_id, principal)

        # Distinguish "model omitted from body" (leave alone) from "model
        # set to null" (clear). Pydantic represents both as None, so we
        # peek at the raw `model_fields_set` to disambiguate.
        clear_model = "model" in request.model_fields_set and request.model is None
        updated = await self.members_for_listing.update(
            agent_id,
            name=request.name,
            priority=request.priority,
            model=request.model if not clear_model else None,
            clear_model=clear_model,
        )
        return AgentResponse.from_entity(updated)

    async def delete_agent(self, agent_id: UUID, principal: Principal) -> None:
        """Hard delete. Refuses with AgentHasCreatedTasksError when the
        agent authored tasks (the FK on tasks.created_by_id is RESTRICT,
        so attempting the delete would IntegrityError anyway — we surface
        the precondition failure with a clearer error). Tasks where the
        agent is the *assignee* get assignee_id set to NULL via the FK
        cascade, preserving their history."""
        await self._load_workspace_agent(agent_id, principal)
        if await self.members_for_listing.has_created_tasks(agent_id):
            raise AgentHasCreatedTasksError(
                "agent created tasks that other members own; reassign or "
                "delete those tasks before removing the agent"
            )
        await self.members_for_listing.delete(agent_id)

    async def _load_workspace_agent(self, agent_id: UUID, principal: Principal) -> Member:
        agent = await self.members_for_listing.get_by_id(agent_id)
        if (
            agent is None
            or agent.workspace_id != principal.workspace_id
            or agent.type is not MemberType.AGENT
        ):
            raise AgentNotFoundError("agent not found")
        return agent
