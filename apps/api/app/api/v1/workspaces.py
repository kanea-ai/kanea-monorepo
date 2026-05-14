"""``/workspaces`` — workspace metadata mutations.

Today: PATCH only — rename. The signup/create flow lives on
``/auth/register`` and ``/me/workspaces``; switcher lives on
``/auth/switch-workspace``. This file is the dedicated owner-only
surface for editing the workspace itself.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.api.deps import PrincipalDep, WorkspaceServiceDep
from app.application.workspaces.schemas import (
    RenameWorkspaceRequest,
    WorkspaceResponse,
)
from app.domain.exceptions import (
    ForbiddenError,
    WorkspaceNameConflictError,
    WorkspaceNotFoundError,
)

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.patch(
    "/{workspace_id}",
    response_model=WorkspaceResponse,
    status_code=status.HTTP_200_OK,
)
async def rename_workspace(
    workspace_id: UUID,
    payload: RenameWorkspaceRequest,
    principal: PrincipalDep,
    service: WorkspaceServiceDep,
) -> WorkspaceResponse:
    """Rename the workspace the requester is logged into.

    Authorization: ``principal.role == WORKSPACE_OWNER`` (the
    workspace's owner is the only one who can rename it) AND the
    path ``workspace_id`` must equal ``principal.workspace_id``.
    Cross-workspace attempts 404 so existence of OTHER workspaces is
    never leaked.

    Conflicts: ``workspaces.name`` is globally unique. A name already
    taken anywhere on the platform → 409.
    """
    try:
        return await service.rename(workspace_id, payload, principal)
    except WorkspaceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except WorkspaceNameConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
