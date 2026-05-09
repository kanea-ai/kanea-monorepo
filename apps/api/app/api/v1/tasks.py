from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.api.deps import PrincipalDep, TaskServiceDep
from app.application.tasks.schemas import (
    CommentResponse,
    CreateCommentRequest,
    CreateTaskRequest,
    DelegateTaskRequest,
    RateTaskRequest,
    SetBlockedRequest,
    TaskRatingResponse,
    TaskResponse,
    UpdateTaskStatusRequest,
)
from app.domain.enums import TaskStatus
from app.domain.exceptions import (
    DelegationForbiddenError,
    InvalidStatusTransitionError,
    RatingForbiddenError,
    TaskAlreadyRatedError,
    TaskNotFoundError,
    TaskNotInDoneStateError,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get(
    "",
    response_model=list[TaskResponse],
    status_code=status.HTTP_200_OK,
)
async def list_tasks(
    principal: PrincipalDep,
    service: TaskServiceDep,
    status_filter: TaskStatus | None = None,
    blocked_only: bool = False,
) -> list[TaskResponse]:
    """List tasks in the requester's workspace, optionally filtered by
    status. The Exception Queue calls this with ``?blocked_only=true``;
    the kanban with no filter."""
    return await service.list_for_workspace(
        principal, status=status_filter, blocked_only=blocked_only
    )


@router.post(
    "",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_task(
    payload: CreateTaskRequest,
    principal: PrincipalDep,
    service: TaskServiceDep,
) -> TaskResponse:
    """Create a new task in the requester's workspace. workspace_id and
    created_by_id are derived from the JWT, never user-supplied — that's
    the tenant-isolation guarantee."""
    try:
        return await service.create(payload, principal)
    except TaskNotFoundError as exc:
        # The only way create surfaces TaskNotFoundError is if the
        # requested assignee_id doesn't exist in the workspace. Return
        # 422 since that's a payload validation issue from the client's
        # perspective, not a missing-task condition.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.get(
    "/{task_id}",
    response_model=TaskResponse,
    status_code=status.HTTP_200_OK,
)
async def get_task(
    task_id: UUID,
    principal: PrincipalDep,
    service: TaskServiceDep,
) -> TaskResponse:
    try:
        return await service.get_by_id(task_id, principal)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/{task_id}/delegate",
    response_model=TaskResponse,
    status_code=status.HTTP_200_OK,
)
async def delegate_task(
    task_id: UUID,
    payload: DelegateTaskRequest,
    principal: PrincipalDep,
    service: TaskServiceDep,
) -> TaskResponse:
    try:
        return await service.delegate(task_id, payload, principal)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DelegationForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.patch(
    "/{task_id}/status",
    response_model=TaskResponse,
    status_code=status.HTTP_200_OK,
)
async def update_task_status(
    task_id: UUID,
    payload: UpdateTaskStatusRequest,
    principal: PrincipalDep,
    service: TaskServiceDep,
) -> TaskResponse:
    try:
        return await service.update_status(task_id, payload, principal)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except InvalidStatusTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.patch(
    "/{task_id}/block",
    response_model=TaskResponse,
    status_code=status.HTTP_200_OK,
)
async def set_task_blocked(
    task_id: UUID,
    payload: SetBlockedRequest,
    principal: PrincipalDep,
    service: TaskServiceDep,
) -> TaskResponse:
    """Toggle the orthogonal blocked flag. Status is untouched —
    a blocked task can still be PENDING or IN_PROGRESS."""
    try:
        return await service.set_blocked(task_id, payload, principal)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/{task_id}/comments",
    response_model=list[CommentResponse],
    status_code=status.HTTP_200_OK,
)
async def list_task_comments(
    task_id: UUID,
    principal: PrincipalDep,
    service: TaskServiceDep,
) -> list[CommentResponse]:
    """Comments on a task, oldest first. Visible to anyone in the
    workspace (humans + agents)."""
    try:
        return await service.list_comments(task_id, principal)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/{task_id}/comments",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_task_comment(
    task_id: UUID,
    payload: CreateCommentRequest,
    principal: PrincipalDep,
    service: TaskServiceDep,
) -> CommentResponse:
    """Append a comment to the task's discussion. Author is the JWT
    holder; agents can post too."""
    try:
        return await service.post_comment(task_id, payload, principal)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/{task_id}/rate",
    response_model=TaskRatingResponse,
    status_code=status.HTTP_201_CREATED,
)
async def rate_task(
    task_id: UUID,
    payload: RateTaskRequest,
    principal: PrincipalDep,
    service: TaskServiceDep,
) -> TaskRatingResponse:
    """Issuer rates the assignee's work after the task lands in DONE.
    One rating per task; the score (0-100) feeds the assignee's
    accuracy stat on the agent dashboard."""
    try:
        return await service.rate_task(task_id, payload, principal)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RatingForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except TaskNotInDoneStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except TaskAlreadyRatedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
