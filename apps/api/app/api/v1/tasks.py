from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status

from app.api.deps import PrincipalDep, TaskServiceDep
from app.application.tasks.schemas import (
    ActivityResponse,
    CommentResponse,
    CreateCommentRequest,
    CreateRelationRequest,
    CreateRequestPayload,
    CreateTaskRequest,
    DelegateTaskRequest,
    RateTaskRequest,
    SetBlockedRequest,
    TaskDetailResponse,
    TaskRatingResponse,
    TaskRelationsResponse,
    TaskRequestResponse,
    TaskResponse,
    UpdateTaskLinksRequest,
    UpdateTaskPriorityRequest,
    UpdateTaskStatusRequest,
)
from app.domain.enums import TaskStatus
from app.domain.exceptions import (
    CrossTeamForbiddenError,
    DelegationForbiddenError,
    InvalidStatusTransitionError,
    ProjectNotFoundError,
    RatingForbiddenError,
    TaskAlreadyRatedError,
    TaskNotFoundError,
    TaskNotInDoneStateError,
    TaskRelationAlreadyExistsError,
    TaskRelationNotFoundError,
    TaskRelationSelfLinkError,
    TaskRequestForbiddenError,
    TeamNotFoundError,
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
    project_id: UUID | None = None,
    team_id: UUID | None = None,
    assignee_id: UUID | None = None,
    priority_min: int | None = None,
    priority_max: int | None = None,
) -> list[TaskResponse]:
    """List tasks in the requester's workspace, optionally filtered.

    RBAC: workspace OWNER / ADMIN see all tasks and can use every
    filter freely; other principals are forced to see only tasks
    where assignee_id = requester (the service silently overrides
    any ?assignee_id query)."""
    return await service.list_for_workspace(
        principal,
        status=status_filter,
        blocked_only=blocked_only,
        project_id=project_id,
        team_id=team_id,
        assignee_id=assignee_id,
        priority_min=priority_min,
        priority_max=priority_max,
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
        # requested assignee_id doesn't exist in the workspace.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except (ProjectNotFoundError, TeamNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except CrossTeamForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.get(
    "/{task_id}",
    response_model=TaskDetailResponse,
    status_code=status.HTTP_200_OK,
)
async def get_task(
    task_id: UUID,
    principal: PrincipalDep,
    service: TaskServiceDep,
) -> TaskDetailResponse:
    """Single-task fetch with the seven relation buckets embedded.
    Agents reading a task get the full linked-work context in one
    round-trip — no extra call to /relations needed."""
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
    "/{task_id}/links",
    response_model=TaskResponse,
    status_code=status.HTTP_200_OK,
)
async def update_task_links(
    task_id: UUID,
    payload: UpdateTaskLinksRequest,
    principal: PrincipalDep,
    service: TaskServiceDep,
) -> TaskResponse:
    """Move the task between projects / teams. Setting either to null
    clears it; omitting the field leaves it untouched."""
    try:
        return await service.update_links(task_id, payload, principal)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (ProjectNotFoundError, TeamNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except CrossTeamForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.patch(
    "/{task_id}/priority",
    response_model=TaskResponse,
    status_code=status.HTTP_200_OK,
)
async def update_task_priority(
    task_id: UUID,
    payload: UpdateTaskPriorityRequest,
    principal: PrincipalDep,
    service: TaskServiceDep,
) -> TaskResponse:
    """Phase 4. Workspace OWNER / ADMIN can edit any task's priority;
    a team's HEAD / MANAGER can edit priority on tasks owned by their
    team. Everyone else gets 403."""
    try:
        return await service.update_priority(task_id, payload, principal)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except CrossTeamForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


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


@router.get(
    "/{task_id}/activity",
    response_model=list[ActivityResponse],
    status_code=status.HTTP_200_OK,
)
async def list_task_activity(
    task_id: UUID,
    principal: PrincipalDep,
    service: TaskServiceDep,
) -> list[ActivityResponse]:
    """Chronological audit log for the task — status flips, blocks,
    moves, ratings. Agents read this alongside the comment thread to
    reconstruct what happened on the task."""
    try:
        return await service.list_activity(task_id, principal)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/{task_id}/relations",
    response_model=TaskRelationsResponse,
    status_code=status.HTTP_200_OK,
)
async def list_task_relations(
    task_id: UUID,
    principal: PrincipalDep,
    service: TaskServiceDep,
) -> TaskRelationsResponse:
    """All directional relations grouped into the seven UI buckets:
    blocks / blocked_by / mitigates / mitigated_by / duplicates /
    duplicated_by / relates_to."""
    try:
        return await service.list_relations(task_id, principal)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/{task_id}/relations",
    status_code=status.HTTP_201_CREATED,
    response_class=Response,
)
async def create_task_relation(
    task_id: UUID,
    payload: CreateRelationRequest,
    principal: PrincipalDep,
    service: TaskServiceDep,
) -> Response:
    """Link two tasks. The link is directional for BLOCKS / MITIGATES /
    DUPLICATES; symmetric for RELATES_TO. 409 if the same relation
    already exists; 400 on a self-link."""
    try:
        await service.create_relation(task_id, payload, principal)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except TaskRelationSelfLinkError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except TaskRelationAlreadyExistsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_201_CREATED)


@router.delete(
    "/{task_id}/relations/{relation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_task_relation(
    task_id: UUID,
    relation_id: UUID,
    principal: PrincipalDep,
    service: TaskServiceDep,
) -> Response:
    try:
        await service.delete_relation(task_id, relation_id, principal)
    except (TaskNotFoundError, TaskRelationNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{task_id}/requests",
    response_model=TaskRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_task_request(
    task_id: UUID,
    payload: CreateRequestPayload,
    principal: PrincipalDep,
    service: TaskServiceDep,
) -> TaskRequestResponse:
    """File a cross-team request anchored to this task. The source
    team's leadership picks it up via /teams/{id}/inbox."""
    try:
        return await service.create_request(task_id, payload, principal)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except TeamNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except TaskRequestForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.get(
    "/{task_id}/requests",
    response_model=list[TaskRequestResponse],
    status_code=status.HTTP_200_OK,
)
async def list_task_requests(
    task_id: UUID,
    principal: PrincipalDep,
    service: TaskServiceDep,
) -> list[TaskRequestResponse]:
    try:
        return await service.list_requests_for_task(task_id, principal)
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
