from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.domain.entities import User


@dataclass(slots=True)
class PlatformSummaryAggregates:
    """Three top-level counters returned by ``get_summary`` in one
    SQL pass."""

    total_active_workspaces: int
    total_registered_users: int
    total_tokens_used: int


@runtime_checkable
class AdminMetricsRepository(Protocol):
    """Cross-tenant platform counters served to the back-office
    dashboard. The contract is "one round-trip per panel" — the
    summary aggregates land in a single SELECT and the recent signups
    list is a separate (indexed) ``users WHERE created_at >= ...``
    scan."""

    async def get_summary(self) -> PlatformSummaryAggregates: ...

    async def list_recent_signups(self, *, since_days: int = 7, limit: int = 50) -> list[User]: ...
