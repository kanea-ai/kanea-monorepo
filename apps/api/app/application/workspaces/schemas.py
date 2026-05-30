from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.entities import Workspace


class RenameWorkspaceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)


class WorkspaceResponse(BaseModel):
    """Compact workspace shape returned by the workspace router.
    Other surfaces (``/me/workspaces``, ``/auth/login``) carry their
    own per-context shapes; this one is the canonical
    full-row response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    task_prefix: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_entity(cls, ws: Workspace) -> WorkspaceResponse:
        return cls(
            id=ws.id,
            name=ws.name,
            slug=ws.slug,
            task_prefix=ws.task_prefix,
            created_at=ws.created_at,
            updated_at=ws.updated_at,
        )
