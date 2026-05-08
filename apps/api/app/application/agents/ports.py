from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from app.domain.entities import AgentStats, Member


@runtime_checkable
class AgentMemberRepository(Protocol):
    """Workspace-scoped queries for agent-typed members. Distinct protocol
    from the auth-side MemberRepository so each application module
    declares only what it depends on."""

    async def list_agents_for_workspace(self, workspace_id: UUID) -> list[Member]: ...
    async def get_by_id(self, member_id: UUID) -> Member | None: ...
    async def update(
        self,
        member_id: UUID,
        *,
        name: str | None = None,
        priority: int | None = None,
        model: str | None = None,
        clear_model: bool = False,
    ) -> Member: ...
    async def delete(self, member_id: UUID) -> None: ...
    async def has_created_tasks(self, member_id: UUID) -> bool: ...
    async def compute_agent_stats(self, agent_id: UUID) -> AgentStats: ...
