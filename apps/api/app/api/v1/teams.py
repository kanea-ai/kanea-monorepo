from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.api.deps import PrincipalDep, TeamReachDep, TeamServiceDep
from app.application.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, Page
from app.application.teams.schemas import (
    CreateTeamRequest,
    TeamResponse,
    UpdateTeamRequest,
)
from app.domain.exceptions import (
    DepartmentNotFoundError,
    TeamNameConflictError,
    TeamNotFoundError,
)

router = APIRouter(prefix="/teams", tags=["teams"])


@router.get(
    "",
    response_model=Page[TeamResponse],
    status_code=status.HTTP_200_OK,
)
async def list_teams(
    principal: PrincipalDep,
    service: TeamServiceDep,
    department_id: Annotated[UUID | None, Query()] = None,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> Page[TeamResponse]:
    """Paginated list of teams in the requester's workspace.

    ``?department_id`` scopes to a single department.
    ``?skip`` / ``?limit`` page through the result set; the response
    body always includes the unfiltered ``total`` count so the UI
    can render page-number controls.
    """
    return await service.list_for_workspace(
        principal, department_id=department_id, skip=skip, limit=limit
    )


@router.post(
    "",
    response_model=TeamResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_team(
    payload: CreateTeamRequest,
    principal: TeamReachDep,
    service: TeamServiceDep,
) -> TeamResponse:
    """Workspace owners / admins only — section 1 RBAC requirement."""
    try:
        return await service.create(payload, principal)
    except TeamNameConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except DepartmentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch(
    "/{team_id}",
    response_model=TeamResponse,
    status_code=status.HTTP_200_OK,
)
async def update_team(
    team_id: UUID,
    payload: UpdateTeamRequest,
    principal: TeamReachDep,
    service: TeamServiceDep,
) -> TeamResponse:
    try:
        return await service.update(team_id, payload, principal)
    except TeamNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DepartmentNotFoundError as exc:
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
    principal: TeamReachDep,
    service: TeamServiceDep,
) -> Response:
    try:
        await service.delete(team_id, principal)
    except TeamNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
