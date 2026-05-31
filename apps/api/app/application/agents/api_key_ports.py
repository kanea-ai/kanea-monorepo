from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID

from app.domain.entities import AgentApiKey


@runtime_checkable
class AgentApiKeyRepository(Protocol):
    """Persistence for per-agent API keys. The exchange path is
    HMAC-keyed lookup → single indexed SELECT → conditional UPDATE
    (last_used_at + member.last_seen_at), all inside one transaction.
    """

    async def create(self, key: AgentApiKey) -> AgentApiKey: ...

    async def list_for_member(self, member_id: UUID) -> list[AgentApiKey]:
        """Newest-first listing for the back-office / agent detail panel."""
        ...

    async def get_by_id(self, key_id: UUID) -> AgentApiKey | None: ...

    async def find_active_by_secret_hash(self, secret_hash: str) -> AgentApiKey | None:
        """Exchange-time lookup. Only returns rows where
        ``revoked_at IS NULL`` — revoked keys are invisible to the
        verification path."""
        ...

    async def mark_used(self, key_id: UUID, *, used_at: datetime) -> None:
        """Stamp ``last_used_at`` after a successful exchange. Called
        in the same transaction as ``members.heartbeat`` so the two
        timestamps can't drift."""
        ...

    async def revoke(self, key_id: UUID, *, revoked_at: datetime) -> bool:
        """Soft-revoke. Returns ``True`` if the row moved from active to
        revoked, ``False`` if it was already revoked or didn't exist —
        lets the caller stay idempotent without an extra round-trip."""
        ...
