from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.application.admin.ports import AdminWorkspaceRepository
from app.application.admin.schemas import (
    AdminWorkspaceRow,
    SuspendWorkspaceRequest,
    WorkspaceMetrics,
)
from app.application.pagination import Page
from app.domain.exceptions import WorkspaceNotFoundError

# Allowed sort keys mirror the query-param shape. Kept here (rather
# than the route) so the service is testable without spinning up an
# HTTP client.
_VALID_SORTS = frozenset(
    {
        "created_at_desc",
        "created_at_asc",
        "name_asc",
        "name_desc",
        "suspended_at_desc",
    }
)


@dataclass(slots=True)
class AdminWorkspaceService:
    workspaces: AdminWorkspaceRepository

    async def list_workspaces(
        self,
        *,
        name: str | None = None,
        sort: str = "created_at_desc",
        skip: int = 0,
        limit: int = 25,
    ) -> Page[AdminWorkspaceRow]:
        """Paginated cross-tenant workspace listing with per-row
        aggregated metrics (users / tasks / tokens). One SQL pass; no
        N+1.

        Unknown ``sort`` values fall back to ``created_at_desc`` —
        we'd rather show *something* than 400 the operator's typo on
        the back-office grid."""
        if sort not in _VALID_SORTS:
            sort = "created_at_desc"
        rows, total = await self.workspaces.list_with_metrics(
            name=name, sort=sort, skip=skip, limit=limit
        )
        return Page[AdminWorkspaceRow](
            items=[
                AdminWorkspaceRow(
                    id=r.workspace.id,
                    name=r.workspace.name,
                    slug=r.workspace.slug,
                    task_prefix=r.workspace.task_prefix,
                    suspended_at=r.workspace.suspended_at,
                    created_at=r.workspace.created_at,
                    updated_at=r.workspace.updated_at,
                    metrics=WorkspaceMetrics(
                        total_users=r.total_users,
                        total_tasks=r.total_tasks,
                        total_tokens_used=r.total_tokens_used,
                    ),
                )
                for r in rows
            ],
            total=total,
        )

    async def set_suspended(
        self, workspace_id: UUID, request: SuspendWorkspaceRequest
    ) -> AdminWorkspaceRow:
        """Flip the soft-suspension stamp.

        - ``is_suspended=True`` sets ``suspended_at = now()`` (idempotent
          if already suspended — we keep the original stamp so the
          audit trail in the DB stays honest).
        - ``is_suspended=False`` clears the column.

        Either way we return the updated row in the same admin shape
        used by the listing so the UI can patch in place. Metrics are
        re-fetched in one call so the suspension flip surfaces a
        consistent row."""
        current = await self.workspaces.get_by_id(workspace_id)
        if current is None:
            raise WorkspaceNotFoundError("workspace not found")

        if request.is_suspended and current.suspended_at is None:
            updated = await self.workspaces.set_suspended_at(workspace_id, datetime.now(UTC))
        elif not request.is_suspended and current.suspended_at is not None:
            updated = await self.workspaces.set_suspended_at(workspace_id, None)
        else:
            updated = current

        # Refresh metrics inline so the suspend response carries the
        # current numbers — saves the frontend a second list call to
        # re-render the row.
        users, tasks, tokens = await self.workspaces.get_metrics(workspace_id)
        metrics = WorkspaceMetrics(total_users=users, total_tasks=tasks, total_tokens_used=tokens)
        return AdminWorkspaceRow(
            id=updated.id,
            name=updated.name,
            slug=updated.slug,
            task_prefix=updated.task_prefix,
            suspended_at=updated.suspended_at,
            created_at=updated.created_at,
            updated_at=updated.updated_at,
            metrics=metrics,
        )
