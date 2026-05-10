from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

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
    MemberFilters,
    MemberResponse,
    MemberStatsResponse,
    SetMemberTeamRequest,
    UpdateMemberProfileRequest,
)
from app.domain.enums import MemberRole
from app.domain.exceptions import (
    EmailAlreadyExistsError,
    ForbiddenError,
    InvalidMemberTypeError,
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
async def list_members(
    principal: PrincipalDep,
    service: InviteServiceDep,
    name: Annotated[str | None, Query(max_length=120)] = None,
    member_id: Annotated[UUID | None, Query()] = None,
    role: Annotated[MemberRole | None, Query()] = None,
    team_id: Annotated[UUID | None, Query()] = None,
    project_id: Annotated[UUID | None, Query()] = None,
    humans_only: Annotated[bool, Query()] = False,
) -> list[MemberResponse]:
    """Visibility-aware members directory. Admins/owners see everyone;
    everyone else sees their team plus themselves. Filters narrow the
    result on top of that scope."""
    filters = MemberFilters(
        name=name,
        member_id=member_id,
        role=role,
        team_id=team_id,
        project_id=project_id,
        humans_only=humans_only,
    )
    members = await service.list_workspace_members(principal, filters)
    return [MemberResponse.from_entity(m) for m in members]


@router.get(
    "/members/{member_id}",
    response_model=MemberResponse,
)
async def get_member(
    member_id: UUID,
    principal: PrincipalDep,
    service: InviteServiceDep,
) -> MemberResponse:
    """Single-member fetch. Same visibility rule as the list endpoint:
    admins see anyone in the workspace; everyone else can only fetch
    themselves or a teammate."""
    try:
        member = await service.get_member(member_id, principal)
    except InvalidMemberTypeError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return MemberResponse.from_entity(member)


@router.get(
    "/members/{member_id}/stats",
    response_model=MemberStatsResponse,
)
async def get_member_stats(
    member_id: UUID,
    principal: PrincipalDep,
    service: InviteServiceDep,
) -> MemberStatsResponse:
    """Per-member stats panel for the directory detail dialog. Same
    visibility rule as GET /members/{id}: admins see anyone, everyone
    else only sees themselves or a teammate."""
    try:
        stats = await service.get_member_stats(member_id, principal)
    except InvalidMemberTypeError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return MemberStatsResponse(
        assigned_count=stats.assigned_count,
        completed_count=stats.completed_count,
        avg_resolution_seconds=stats.avg_resolution_seconds,
        accuracy_percent=stats.accuracy_percent,
        last_activity_at=stats.last_activity_at,
        total_tokens_used=stats.total_tokens_used,
    )


@router.patch(
    "/members/{member_id}",
    response_model=MemberResponse,
)
async def update_member_profile(
    member_id: UUID,
    payload: UpdateMemberProfileRequest,
    admin: WorkspaceAdminDep,
    service: InviteServiceDep,
) -> MemberResponse:
    """Admin-only edit of a member's display name and/or workspace
    role. The "last owner" invariant is enforced at the service layer:
    you can't demote the last WORKSPACE_OWNER."""
    try:
        member = await service.update_member_profile(member_id, payload, admin)
    except InvalidMemberTypeError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return MemberResponse.from_entity(member)


@router.patch(
    "/members/{member_id}/team",
    response_model=MemberResponse,
    status_code=status.HTTP_200_OK,
)
async def set_member_team(
    member_id: UUID,
    payload: SetMemberTeamRequest,
    admin: WorkspaceAdminDep,
    service: InviteServiceDep,
) -> MemberResponse:
    """Workspace admins assign a member to a Team and set their
    intra-team role. Use team_id=null to unassign."""
    try:
        member = await service.set_member_team(member_id, payload, admin)
    except InvalidMemberTypeError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return MemberResponse.from_entity(member)
