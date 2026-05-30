from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from uuid import UUID

from app.domain.entities import Workspace


# Dataclass-style tuple-with-metrics row returned by ``list_with_metrics``.
# Defined here (next to the Protocol) so the service can depend on the
# port without dragging in the SqlAlchemy infrastructure.
@dataclass(slots=True)
class WorkspaceRowWithMetrics:
    workspace: Workspace
    total_users: int
    total_tasks: int
    total_tokens_used: int


@runtime_checkable
class AdminWorkspaceRepository(Protocol):
    """Cross-tenant workspace surface served to the back-office. The
    listing query joins ``members`` + ``tasks`` so a single round-trip
    populates the metrics column."""

    async def list_with_metrics(
        self,
        *,
        name: str | None = None,
        sort: str = "created_at_desc",
        skip: int = 0,
        limit: int = 25,
    ) -> tuple[list[WorkspaceRowWithMetrics], int]: ...

    async def get_by_id(self, workspace_id: UUID) -> Workspace | None: ...

    async def set_suspended_at(self, workspace_id: UUID, suspended_at) -> Workspace: ...

    async def get_metrics(self, workspace_id: UUID) -> tuple[int, int, int]:
        """Returns ``(total_users, total_tasks, total_tokens_used)`` for
        a single workspace in one SQL pass. Used by the suspend / restore
        flow so the response carries fresh numbers without re-paging."""
        ...
