from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.application.agents.api_key_ports import AgentApiKeyRepository
from app.application.agents.ports import AgentMemberRepository
from app.application.agents.schemas import (
    AgentApiKeyResponse,
    AgentDetailResponse,
    AgentResponse,
    AgentStatsResponse,
    CreateAgentRequest,
    CreateAgentResponse,
    IssueAgentApiKeyRequest,
    IssueAgentApiKeyResponse,
    UpdateAgentRequest,
)
from app.application.auth.ports import MemberRepository
from app.application.tasks.schemas import Principal
from app.domain.entities import AgentApiKey, Member
from app.domain.enums import MemberRole, MemberType
from app.domain.exceptions import (
    AgentApiKeyNotFoundError,
    AgentHasCreatedTasksError,
    AgentNotFoundError,
    ForbiddenError,
)
from app.infrastructure.security.agent_api_keys import MintedKey, mint

# Health-status thresholds. ONLINE ≤ 5 min, IDLE ≤ 1 h, STALE otherwise.
# Tuned for an LLM agent loop that pings every 30-90s while working —
# anything older than 5 min means the loop is paused or the agent
# crashed; older than an hour means it's effectively offline.
_ONLINE_WINDOW = timedelta(minutes=5)
_IDLE_WINDOW = timedelta(hours=1)


def derive_health_status(last_seen_at: datetime | None) -> str:
    """Maps last_seen_at -> 'ONLINE'|'IDLE'|'STALE'. Pure so it's cheap
    to test; called from get_agent_detail at request time rather than
    persisted on the row (which would require a clock-driven sweep)."""
    if last_seen_at is None:
        return "STALE"
    # Tolerate naïve datetimes coming back from the DB by assuming UTC —
    # SQLAlchemy with timezone=True should always yield aware values, but
    # belt-and-braces for migration-era rows.
    if last_seen_at.tzinfo is None:
        last_seen_at = last_seen_at.replace(tzinfo=UTC)
    delta = datetime.now(UTC) - last_seen_at
    if delta <= _ONLINE_WINDOW:
        return "ONLINE"
    if delta <= _IDLE_WINDOW:
        return "IDLE"
    return "STALE"


@dataclass(slots=True)
class AgentService:
    members_for_listing: AgentMemberRepository
    auth_members: MemberRepository
    api_keys: AgentApiKeyRepository
    env_tag: str
    pepper: str

    async def create_agent(
        self, request: CreateAgentRequest, principal: Principal
    ) -> CreateAgentResponse:
        """Provision a new AGENT-typed member in the requester's workspace
        and mint a first API key in the same response. Subsequent keys go
        through ``POST /agents/{id}/api-keys``.

        Admin-gating is enforced at the route layer (WorkspaceAdminDep);
        the service trusts the principal but re-asserts the role here as
        belt-and-braces — agents must not be self-provisioned by other
        agents, regardless of how the route is wired.
        """
        if principal.role not in (MemberRole.WORKSPACE_OWNER, MemberRole.WORKSPACE_ADMIN):
            raise ForbiddenError("workspace owner or admin role required")

        now = datetime.now(UTC)
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
                role=MemberRole.WORKSPACE_USER,
                model=request.model,
                created_at=now,
                updated_at=now,
            )
        )
        minted = mint(env_tag=self.env_tag, pepper=self.pepper)
        await self._persist_key(
            member_id=member.id,
            created_by_member_id=principal.member_id,
            minted=minted,
            label=None,
        )
        return CreateAgentResponse(
            id=member.id,
            workspace_id=member.workspace_id,
            name=member.name,
            priority=member.priority,
            model=member.model,
            api_key=minted.plaintext,
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
            last_seen_at=agent.last_seen_at,
            health_status=derive_health_status(agent.last_seen_at),
            stats=AgentStatsResponse.from_entity(stats),
        )

    async def heartbeat(self, principal: Principal) -> None:
        """Stamp last_seen_at on the calling agent's row. The router
        already enforces scope==agent so we trust the principal here;
        any human-issued JWT would be rejected before reaching us."""
        await self.members_for_listing.heartbeat(principal.member_id)

    async def update_agent(
        self, agent_id: UUID, request: UpdateAgentRequest, principal: Principal
    ) -> AgentResponse:
        """Partial update of name/priority/model. id stays immutable; an
        empty body is a 200 no-op (Pydantic happily accepts {}).

        Admin-gating is at the route layer (WorkspaceAdminDep, per #46);
        the service re-asserts the role here as belt-and-braces, same
        pattern as ``create_agent``. Agents must not be reconfigured
        by non-admin members regardless of how the route is wired.
        """
        if principal.role not in (MemberRole.WORKSPACE_OWNER, MemberRole.WORKSPACE_ADMIN):
            raise ForbiddenError("workspace owner or admin role required")
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
        cascade, preserving their history.

        Admin-gating is at the route layer (WorkspaceAdminDep, per #46);
        the service re-asserts the role here as belt-and-braces.
        """
        if principal.role not in (MemberRole.WORKSPACE_OWNER, MemberRole.WORKSPACE_ADMIN):
            raise ForbiddenError("workspace owner or admin role required")
        await self._load_workspace_agent(agent_id, principal)
        if await self.members_for_listing.has_created_tasks(agent_id):
            raise AgentHasCreatedTasksError(
                "agent created tasks that other members own; reassign or "
                "delete those tasks before removing the agent"
            )
        await self.members_for_listing.delete(agent_id)

    # ---------- API keys ----------

    async def issue_api_key(
        self,
        agent_id: UUID,
        request: IssueAgentApiKeyRequest,
        principal: Principal,
    ) -> IssueAgentApiKeyResponse:
        """Mint an additional key for an existing agent. Plaintext is
        returned exactly once; only the HMAC digest is persisted."""
        if principal.role not in (MemberRole.WORKSPACE_OWNER, MemberRole.WORKSPACE_ADMIN):
            raise ForbiddenError("workspace owner or admin role required")
        await self._load_workspace_agent(agent_id, principal)

        minted = mint(env_tag=self.env_tag, pepper=self.pepper)
        persisted = await self._persist_key(
            member_id=agent_id,
            created_by_member_id=principal.member_id,
            minted=minted,
            label=request.label,
        )
        return IssueAgentApiKeyResponse(
            id=persisted.id,
            prefix=persisted.prefix,
            last4=persisted.last4,
            label=persisted.label,
            created_at=persisted.created_at,
            api_key=minted.plaintext,
        )

    async def list_api_keys(
        self, agent_id: UUID, principal: Principal
    ) -> list[AgentApiKeyResponse]:
        """Metadata-only listing. No plaintext, no hash — just fingerprint
        + timestamps. Admin-gated (consistency with issue / revoke)."""
        if principal.role not in (MemberRole.WORKSPACE_OWNER, MemberRole.WORKSPACE_ADMIN):
            raise ForbiddenError("workspace owner or admin role required")
        await self._load_workspace_agent(agent_id, principal)
        rows = await self.api_keys.list_for_member(agent_id)
        return [AgentApiKeyResponse.from_entity(r) for r in rows]

    async def revoke_api_key(self, agent_id: UUID, key_id: UUID, principal: Principal) -> None:
        """Soft-revoke. Idempotent — already-revoked keys + cross-agent
        key ids both surface as a 404 to the caller (NotFound), keeping
        the cross-tenant probe shape consistent."""
        if principal.role not in (MemberRole.WORKSPACE_OWNER, MemberRole.WORKSPACE_ADMIN):
            raise ForbiddenError("workspace owner or admin role required")
        await self._load_workspace_agent(agent_id, principal)
        row = await self.api_keys.get_by_id(key_id)
        if row is None or row.member_id != agent_id:
            raise AgentApiKeyNotFoundError("api key not found")
        await self.api_keys.revoke(key_id, revoked_at=datetime.now(UTC))

    # ---------- helpers ----------

    async def _persist_key(
        self,
        *,
        member_id: UUID,
        created_by_member_id: UUID,
        minted: MintedKey,
        label: str | None,
    ) -> AgentApiKey:
        return await self.api_keys.create(
            AgentApiKey(
                id=uuid4(),
                member_id=member_id,
                secret_hash=minted.secret_hash,
                prefix=minted.prefix,
                last4=minted.last4,
                label=label,
                created_by_member_id=created_by_member_id,
                created_at=datetime.now(UTC),
            )
        )

    async def _load_workspace_agent(self, agent_id: UUID, principal: Principal) -> Member:
        agent = await self.members_for_listing.get_by_id(agent_id)
        if (
            agent is None
            or agent.workspace_id != principal.workspace_id
            or agent.type is not MemberType.AGENT
        ):
            raise AgentNotFoundError("agent not found")
        return agent
