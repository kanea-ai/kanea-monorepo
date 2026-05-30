from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class WorkspaceMetrics(BaseModel):
    """Aggregated counters for a single workspace, materialised in one
    SQL pass alongside the listing query. Plain ints with cheap
    additive semantics so the back-office grid can sort / filter on
    them without a second round-trip."""

    model_config = ConfigDict(from_attributes=True)

    total_users: int
    total_tasks: int
    total_tokens_used: int


class AdminWorkspaceRow(BaseModel):
    """One row in ``GET /api/v1/admin/workspaces``. Mirrors the public
    Workspace shape plus the back-office-only ``suspended_at`` and the
    aggregated metrics."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    task_prefix: str
    suspended_at: datetime | None
    created_at: datetime
    updated_at: datetime
    metrics: WorkspaceMetrics


class SuspendWorkspaceRequest(BaseModel):
    """Toggle the workspace-wide suspension. ``true`` sets
    ``suspended_at = now()``; ``false`` clears it back to NULL."""

    model_config = ConfigDict(extra="forbid")

    is_suspended: bool
