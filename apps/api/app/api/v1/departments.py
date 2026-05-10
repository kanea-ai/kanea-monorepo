from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.api.deps import DepartmentReachDep, DepartmentServiceDep, PrincipalDep
from app.application.departments.schemas import (
    CreateDepartmentRequest,
    DepartmentResponse,
    UpdateDepartmentRequest,
)
from app.application.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, Page
from app.domain.exceptions import (
    DepartmentNameConflictError,
    DepartmentNotFoundError,
    ForbiddenError,
)

router = APIRouter(prefix="/departments", tags=["departments"])


@router.get(
    "",
    response_model=Page[DepartmentResponse],
    status_code=status.HTTP_200_OK,
)
async def list_departments(
    principal: PrincipalDep,
    service: DepartmentServiceDep,
    name: Annotated[str | None, Query(max_length=120)] = None,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> Page[DepartmentResponse]:
    """Paginated list of departments. Anyone in the workspace can
    list; only OWNER/ADMIN can mutate. ``name`` is an optional
    case-insensitive substring filter."""
    return await service.list_for_workspace(principal, name=name, skip=skip, limit=limit)


@router.post(
    "",
    response_model=DepartmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_department(
    payload: CreateDepartmentRequest,
    admin: DepartmentReachDep,
    service: DepartmentServiceDep,
) -> DepartmentResponse:
    try:
        return await service.create(payload, admin)
    except DepartmentNameConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.get(
    "/{department_id}",
    response_model=DepartmentResponse,
    status_code=status.HTTP_200_OK,
)
async def get_department(
    department_id: UUID,
    principal: PrincipalDep,
    service: DepartmentServiceDep,
) -> DepartmentResponse:
    try:
        return await service.get_by_id(department_id, principal)
    except DepartmentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch(
    "/{department_id}",
    response_model=DepartmentResponse,
    status_code=status.HTTP_200_OK,
)
async def update_department(
    department_id: UUID,
    payload: UpdateDepartmentRequest,
    admin: DepartmentReachDep,
    service: DepartmentServiceDep,
) -> DepartmentResponse:
    try:
        return await service.update(department_id, payload, admin)
    except DepartmentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DepartmentNameConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.delete(
    "/{department_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_department(
    department_id: UUID,
    admin: DepartmentReachDep,
    service: DepartmentServiceDep,
) -> Response:
    try:
        await service.delete(department_id, admin)
    except DepartmentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
