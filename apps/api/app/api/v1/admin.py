from __future__ import annotations

# Platform back-office surface. Every endpoint under ``/api/v1/admin``
# is gated by ``SuperadminDep`` (the ``get_current_superadmin``
# dependency). Workspace OWNERs cannot reach these routes — the
# ``users.is_superadmin`` flag is platform-level, separate from any
# workspace role.
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import AdminUserServiceDep, AdminWorkspaceServiceDep, SuperadminDep
from app.application.admin.schemas import (
    AdminWorkspaceRow,
    SuspendWorkspaceRequest,
)
from app.application.admin.users_schemas import (
    AdminUserDetail,
    AdminUserRow,
    BanUserRequest,
    ForcePasswordResetResponse,
)
from app.application.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, Page
from app.domain.exceptions import (
    ForbiddenError,
    InvalidMemberTypeError,
    WorkspaceNotFoundError,
)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/health", status_code=status.HTTP_200_OK)
async def admin_health(superadmin: SuperadminDep) -> dict[str, str]:
    """Liveness probe for the back-office surface. Doubles as a
    smoke check that ``SuperadminDep`` is wired: hitting this route
    with any non-superadmin JWT must 403. Returns the resolved
    superadmin's email so the caller can confirm which identity
    passed the gate."""
    return {"status": "ok", "email": superadmin.email}


@router.get(
    "/workspaces",
    response_model=Page[AdminWorkspaceRow],
    status_code=status.HTTP_200_OK,
)
async def list_workspaces(
    _superadmin: SuperadminDep,
    service: AdminWorkspaceServiceDep,
    name: Annotated[str | None, Query(max_length=200)] = None,
    sort: Annotated[str, Query()] = "created_at_desc",
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> Page[AdminWorkspaceRow]:
    """Cross-tenant workspace listing for the back-office grid.

    Filters: ``name`` does a case-insensitive substring match against
    name OR slug. ``sort`` accepts ``created_at_desc`` (default),
    ``created_at_asc``, ``name_asc``, ``name_desc``,
    ``suspended_at_desc``. Unknown sort keys fall back to
    ``created_at_desc`` rather than 400-ing the operator's typo.

    Each row carries aggregated metrics (``total_users``,
    ``total_tasks``, ``total_tokens_used``) computed in the same SQL
    pass as the listing — no N+1."""
    return await service.list_workspaces(name=name, sort=sort, skip=skip, limit=limit)


@router.patch(
    "/workspaces/{workspace_id}/suspend",
    response_model=AdminWorkspaceRow,
    status_code=status.HTTP_200_OK,
)
async def set_workspace_suspended(
    workspace_id: UUID,
    payload: SuspendWorkspaceRequest,
    _superadmin: SuperadminDep,
    service: AdminWorkspaceServiceDep,
) -> AdminWorkspaceRow:
    """Soft-suspend or restore a workspace.

    ``is_suspended=true`` sets ``workspaces.suspended_at`` to now;
    every workspace-scoped JWT for that workspace immediately bounces
    with 403 (see ``get_current_principal``). ``is_suspended=false``
    clears the column. Idempotent on both sides — re-suspending or
    re-restoring keeps the original timestamp.

    Soft suspension by design: no rows are deleted, so the workspace
    can be restored at any time without backup juggling."""
    try:
        return await service.set_suspended(workspace_id, payload)
    except WorkspaceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Global user management.
# ---------------------------------------------------------------------------


@router.get(
    "/users",
    response_model=Page[AdminUserRow],
    status_code=status.HTTP_200_OK,
)
async def list_users(
    _superadmin: SuperadminDep,
    service: AdminUserServiceDep,
    name: Annotated[str | None, Query(max_length=254)] = None,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> Page[AdminUserRow]:
    """Cross-tenant user listing. ``name`` does a case-insensitive
    substring match against email OR full_name. Each row carries the
    user's workspace count so the grid surfaces "this account touches
    N tenants" without a follow-up call."""
    return await service.list_users(name=name, skip=skip, limit=limit)


@router.get(
    "/users/{user_id}",
    response_model=AdminUserDetail,
    status_code=status.HTTP_200_OK,
)
async def get_user_detail(
    user_id: UUID,
    _superadmin: SuperadminDep,
    service: AdminUserServiceDep,
) -> AdminUserDetail:
    """Full back-office profile: identity + every workspace the user
    is a member of with their role + per-membership suspension flag.
    Surfaces the platform-level flags too (``is_superadmin``,
    ``is_banned``, ``sessions_invalidated_at``)."""
    try:
        return await service.get_user_detail(user_id)
    except InvalidMemberTypeError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/users/{user_id}/ban",
    response_model=AdminUserDetail,
    status_code=status.HTTP_200_OK,
)
async def set_user_banned(
    user_id: UUID,
    payload: BanUserRequest,
    superadmin: SuperadminDep,
    service: AdminUserServiceDep,
) -> AdminUserDetail:
    """Set or clear ``users.is_banned``. While True every workspace
    route 403s with ``account banned`` (see ``get_current_principal``).

    Guards:
    - Cannot ban yourself (would lock you out of the back-office).
    - Cannot ban another superadmin via this surface — revoke them
      first via the CLI ``scripts.make_superadmin --revoke``.
    """
    try:
        return await service.set_banned(user_id, payload, principal_user_id=superadmin.id)
    except InvalidMemberTypeError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.post(
    "/users/{user_id}/force-password-reset",
    response_model=ForcePasswordResetResponse,
    status_code=status.HTTP_200_OK,
)
async def force_user_password_reset(
    user_id: UUID,
    superadmin: SuperadminDep,
    service: AdminUserServiceDep,
) -> ForcePasswordResetResponse:
    """Invalidate every outstanding JWT for the user AND randomise
    their password hash so they can't log in until they run the
    account-recovery flow. No real email is sent in this stage; the
    simulated payload is in the response body AND logged at INFO so
    the operator can confirm what would have been delivered."""
    try:
        return await service.force_password_reset(user_id, principal_user_id=superadmin.id)
    except InvalidMemberTypeError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
