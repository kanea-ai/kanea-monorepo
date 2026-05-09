from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.deps import PrincipalDep, get_me_service
from app.application.me.schemas import (
    ChangePasswordRequest,
    MeProfileResponse,
    MeStatsResponse,
    UpdateMeRequest,
)
from app.application.me.service import MeService
from app.domain.exceptions import AuthenticationError, InvalidMemberTypeError

router = APIRouter(prefix="/me", tags=["me"])


MeServiceDep = Annotated[MeService, Depends(get_me_service)]


@router.get("", response_model=MeProfileResponse)
async def get_me(principal: PrincipalDep, service: MeServiceDep) -> MeProfileResponse:
    try:
        return await service.get_profile(principal)
    except InvalidMemberTypeError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch("", response_model=MeProfileResponse)
async def update_me(
    payload: UpdateMeRequest, principal: PrincipalDep, service: MeServiceDep
) -> MeProfileResponse:
    try:
        return await service.update_profile(principal, payload)
    except InvalidMemberTypeError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def change_password(
    payload: ChangePasswordRequest, principal: PrincipalDep, service: MeServiceDep
) -> Response:
    try:
        await service.change_password(principal, payload)
    except AuthenticationError as exc:
        # 401 is reserved for "your token is bad" — wrong current
        # password is a 400 (the request was authenticated, the body is
        # invalid). Matches what most apis do for password change.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except InvalidMemberTypeError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/stats", response_model=MeStatsResponse)
async def get_stats(principal: PrincipalDep, service: MeServiceDep) -> MeStatsResponse:
    return await service.get_stats(principal)
