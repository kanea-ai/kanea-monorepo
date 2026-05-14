from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.application.auth.service import _generate_slug
from app.application.tasks.schemas import Principal
from app.application.workspaces.ports import WorkspaceWriteRepository
from app.application.workspaces.schemas import (
    RenameWorkspaceRequest,
    WorkspaceResponse,
)
from app.domain.enums import MemberRole
from app.domain.exceptions import (
    ForbiddenError,
    WorkspaceNameConflictError,
    WorkspaceNotFoundError,
)


@dataclass(slots=True)
class WorkspaceService:
    """Workspace-level mutations. Today: rename only — owners-only
    because the workspace name is the tenant's public identity and
    its slug is part of every URL we'll eventually expose."""

    workspaces: WorkspaceWriteRepository

    async def rename(
        self,
        workspace_id: UUID,
        request: RenameWorkspaceRequest,
        principal: Principal,
    ) -> WorkspaceResponse:
        # Path id must match the JWT's workspace_id. Cross-workspace
        # attempts surface as not-found so existence isn't leaked —
        # 404 is the same shape we use everywhere else for tenant
        # isolation.
        if workspace_id != principal.workspace_id:
            raise WorkspaceNotFoundError("workspace not found")

        # Role check sits BEFORE the load so a non-owner request
        # doesn't generate a stray DB read.
        if principal.role is not MemberRole.WORKSPACE_OWNER:
            raise ForbiddenError("workspace owner role required")

        current = await self.workspaces.get_by_id(workspace_id)
        if current is None:
            # Edge case: JWT references a workspace_id that no longer
            # exists (e.g. deleted out of band). Same 404 shape.
            raise WorkspaceNotFoundError("workspace not found")

        new_name = request.name.strip()
        if new_name == current.name:
            # No-op short-circuit. Keeps the audit trail tidy and
            # avoids a spurious unique-constraint hit when the slug
            # gets regenerated against itself.
            return WorkspaceResponse.from_entity(current)

        # Slug always regenerates from the new name. The generator
        # appends a 6-hex-char suffix so the slug column won't
        # collide; the DB's unique constraint on ``slug`` is the
        # belt to the braces.
        new_slug = _generate_slug(new_name)

        try:
            updated = await self.workspaces.rename(workspace_id, name=new_name, slug=new_slug)
        except IntegrityError as exc:
            # The UNIQUE constraint on ``workspaces.name`` (migration
            # 0016) maps cleanly to 409 at the route — see
            # ``app/api/v1/workspaces.py``.
            raise WorkspaceNameConflictError("a workspace with that name already exists") from exc
        return WorkspaceResponse.from_entity(updated)
