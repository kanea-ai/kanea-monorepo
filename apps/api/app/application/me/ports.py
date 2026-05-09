from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from app.domain.entities import AgentStats, Member


@runtime_checkable
class MeMemberRepository(Protocol):
    """Read + stats surface needed by the /me endpoints. The same
    SQLAlchemy implementation backs MemberRepository / AgentMember-
    Repository / TenantMemberRepository — we just declare a separate
    Protocol so the service depends only on what it uses."""

    async def get_by_id(self, member_id: UUID) -> Member | None: ...
    async def compute_agent_stats(self, member_id: UUID) -> AgentStats: ...
