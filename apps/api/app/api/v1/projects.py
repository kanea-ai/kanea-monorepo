from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.api.deps import PrincipalDep, ProjectServiceDep, TaskServiceDep
from app.application.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, Page
from app.application.projects.schemas import (
    CreateProjectRequest,
    ProjectHistoryResponse,
    ProjectResponse,
    UpdateProjectRequest,
)
from app.application.tasks.schemas import TaskResponse
from app.domain.exceptions import ProjectNameConflictError, ProjectNotFoundError

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get(
    "",
    response_model=Page[ProjectResponse],
    status_code=status.HTTP_200_OK,
)
async def list_projects(
    principal: PrincipalDep,
    service: ProjectServiceDep,
    include_archived: bool = False,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> Page[ProjectResponse]:
    """Paginated list of projects in the requester's workspace.
    ARCHIVED projects are hidden by default; pass
    ``?include_archived=true`` to see them. Pagination is via
    ``?skip``/``?limit`` and the response carries the unfiltered
    ``total`` count."""
    return await service.list_for_workspace(
        principal, include_archived=include_archived, skip=skip, limit=limit
    )


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_project(
    payload: CreateProjectRequest,
    principal: PrincipalDep,
    service: ProjectServiceDep,
) -> ProjectResponse:
    try:
        return await service.create(payload, principal)
    except ProjectNameConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
    status_code=status.HTTP_200_OK,
)
async def get_project(
    project_id: UUID,
    principal: PrincipalDep,
    service: ProjectServiceDep,
) -> ProjectResponse:
    try:
        return await service.get_by_id(project_id, principal)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch(
    "/{project_id}",
    response_model=ProjectResponse,
    status_code=status.HTTP_200_OK,
)
async def update_project(
    project_id: UUID,
    payload: UpdateProjectRequest,
    principal: PrincipalDep,
    service: ProjectServiceDep,
) -> ProjectResponse:
    try:
        return await service.update(project_id, payload, principal)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ProjectNameConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_project(
    project_id: UUID,
    principal: PrincipalDep,
    service: ProjectServiceDep,
) -> Response:
    try:
        await service.delete(project_id, principal)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{project_id}/history",
    response_model=ProjectHistoryResponse,
    status_code=status.HTTP_200_OK,
)
async def get_project_history(
    project_id: UUID,
    principal: PrincipalDep,
    project_service: ProjectServiceDep,
) -> ProjectHistoryResponse:
    """Single-shot bundle for the AI history endpoint. Returns the
    project, its tasks, the audit log per task, the comment thread per
    task, and per-task ratings — plus a summary of status mix, blocked
    count, average resolution and total tokens. Cheaper for an agent
    than walking the per-resource endpoints."""
    try:
        return await project_service.compute_history(project_id, principal)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/{project_id}/tasks",
    response_model=list[TaskResponse],
    status_code=status.HTTP_200_OK,
)
async def list_project_tasks(
    project_id: UUID,
    principal: PrincipalDep,
    project_service: ProjectServiceDep,
    task_service: TaskServiceDep,
) -> list[TaskResponse]:
    """Tasks scoped to this project. The project lookup also enforces
    tenant isolation — a stranger's project id 404s."""
    try:
        await project_service.get_by_id(project_id, principal)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return await task_service.list_for_workspace(principal, project_id=project_id)
