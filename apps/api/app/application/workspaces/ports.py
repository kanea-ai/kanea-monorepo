from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from app.domain.entities import Workspace


@runtime_checkable
class WorkspaceWriteRepository(Protocol):
    """Mutation surface for workspace metadata. Distinct from the
    auth-flow ``WorkspaceRepository`` (which only does create/get) so
    services that just *write* don't accidentally depend on the
    creation surface."""

    async def get_by_id(self, workspace_id: UUID) -> Workspace | None: ...
    async def rename(self, workspace_id: UUID, *, name: str, slug: str) -> Workspace: ...
