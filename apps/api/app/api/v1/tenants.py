from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.deps import (
    InviteServiceDep,
    PrincipalDep,
    WorkspaceAdminDep,
)
from app.application.auth.schemas import TokenResponse
from app.application.tenants.schemas import (
    InviteAcceptRequest,
    InviteCreateRequest,
    InviteCreateResponse,
    InvitePreviewResponse,
    MemberResponse,
)
from app.domain.exceptions import (
    EmailAlreadyExistsError,
    ForbiddenError,
    InviteAlreadyAcceptedError,
    InviteExpiredError,
    InviteNotFoundError,
)

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.post(
    "/invites",
    response_model=InviteCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_invite(
    payload: InviteCreateRequest,
    admin: WorkspaceAdminDep,
    service: InviteServiceDep,
) -> InviteCreateResponse:
    try:
        return await service.create_invite(payload, admin)
    except ForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.get(
    "/invites/{token}",
    response_model=InvitePreviewResponse,
)
async def get_invite_preview(token: str, service: InviteServiceDep) -> InvitePreviewResponse:
    """Anonymous endpoint — by design, knowing the token is the only check.
    Returns minimal info (workspace name, invited email, role, expiry) so a
    leaked token reveals as little as possible."""
    try:
        return await service.get_invite_preview(token)
    except InviteNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except InviteExpiredError as exc:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(exc)) from exc
    except InviteAlreadyAcceptedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post(
    "/invites/{token}/accept",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
)
async def accept_invite(
    token: str,
    payload: InviteAcceptRequest,
    service: InviteServiceDep,
) -> TokenResponse:
    """Anonymous accept flow. Creates a Member with the invited role, sets
    the password from the request, and returns a JWT so the new user is
    auto-logged-in into the target workspace."""
    try:
        return await service.accept_invite(token, payload)
    except InviteNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except InviteExpiredError as exc:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(exc)) from exc
    except InviteAlreadyAcceptedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except EmailAlreadyExistsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get(
    "/members",
    response_model=list[MemberResponse],
)
async def list_members(principal: PrincipalDep, service: InviteServiceDep) -> list[MemberResponse]:
    members = await service.list_workspace_members(principal)
    return [MemberResponse.from_entity(m) for m in members]
