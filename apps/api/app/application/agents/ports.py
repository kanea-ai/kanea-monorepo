from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from app.domain.entities import Member


@runtime_checkable
class AgentMemberRepository(Protocol):
    """Workspace-scoped queries for agent-typed members. Distinct protocol
    from the auth-side MemberRepository so each application module
    declares only what it depends on."""

    async def list_agents_for_workspace(self, workspace_id: UUID) -> list[Member]: ...
