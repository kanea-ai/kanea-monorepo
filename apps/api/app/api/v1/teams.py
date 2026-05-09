from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status

from app.api.deps import PrincipalDep, TeamServiceDep
from app.application.teams.schemas import (
    CreateTeamRequest,
    TeamResponse,
    UpdateTeamRequest,
)
from app.domain.exceptions import TeamNameConflictError, TeamNotFoundError

router = APIRouter(prefix="/teams", tags=["teams"])


@router.get(
    "",
    response_model=list[TeamResponse],
    status_code=status.HTTP_200_OK,
)
async def list_teams(
    principal: PrincipalDep,
    service: TeamServiceDep,
) -> list[TeamResponse]:
    return await service.list_for_workspace(principal)


@router.post(
    "",
    response_model=TeamResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_team(
    payload: CreateTeamRequest,
    principal: PrincipalDep,
    service: TeamServiceDep,
) -> TeamResponse:
    try:
        return await service.create(payload, principal)
    except TeamNameConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.patch(
    "/{team_id}",
    response_model=TeamResponse,
    status_code=status.HTTP_200_OK,
)
async def update_team(
    team_id: UUID,
    payload: UpdateTeamRequest,
    principal: PrincipalDep,
    service: TeamServiceDep,
) -> TeamResponse:
    try:
        return await service.update(team_id, payload, principal)
    except TeamNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except TeamNameConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.delete(
    "/{team_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_team(
    team_id: UUID,
    principal: PrincipalDep,
    service: TeamServiceDep,
) -> Response:
    try:
        await service.delete(team_id, principal)
    except TeamNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
