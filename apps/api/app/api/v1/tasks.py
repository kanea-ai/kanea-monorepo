from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.api.deps import PrincipalDep, TaskServiceDep
from app.application.tasks.schemas import DelegateTaskRequest, TaskResponse
from app.domain.exceptions import DelegationForbiddenError, TaskNotFoundError

router = APIRouter(prefix="/tasks", tags=["tasks"])


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
