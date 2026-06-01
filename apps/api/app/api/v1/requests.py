"""Resolution endpoints for cross-team task requests.

Creation lives on /tasks/{id}/requests (the request is anchored to a
source task). Resolution sits on its own collection because a
fulfilled request mints a brand new task — that doesn't fit cleanly
under the source-task tree.

The team-inbox endpoint mounts on /teams/{team_id}/requests so the
URL reads naturally for the leadership view ("requests filed against
my team's tasks").
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.api.deps import PrincipalDep, TaskServiceDep
from app.application.tasks.schemas import (
    FulfillRequestPayload,
    RejectRequestPayload,
    TaskRequestResponse,
)
from app.domain.enums import RequestStatus
from app.domain.exceptions import (
    TaskNotFoundError,
    TaskRequestAlreadyResolvedError,
    TaskRequestForbiddenError,
    TaskRequestNotFoundError,
    TeamNotFoundError,
)

router = APIRouter(tags=["task-requests"])


@router.get(
    "/teams/{team_id}/requests",
    response_model=list[TaskRequestResponse],
    status_code=status.HTTP_200_OK,
)
async def list_team_inbox_requests(
    team_id: UUID,
    principal: PrincipalDep,
    service: TaskServiceDep,
    direction: str = "incoming",
    status_filter: RequestStatus | None = None,
) -> list[TaskRequestResponse]:
    """Team inbox of cross-team requests.

    ``direction=incoming`` (default) — requests targeting THIS team.
    Use this when you want to see "what have other teams asked us to
    do?" Under the auto-fulfilment model (issue #50 tracks the
    approval-gate alternative) these are typically already ``FULFILLED``
    by the time they appear — the requester has already had a task
    auto-minted on this team's board.

    ``direction=outgoing`` — requests anchored to a source task LIVING
    on this team. Use this to see "what have we asked other teams for?"

    Any workspace member can read either direction. The default
    ``status_filter`` is unset (return all statuses), since under
    auto-fulfilment new requests are born ``FULFILLED`` and a default
    ``PENDING`` filter would silently hide everything."""
    if direction not in ("incoming", "outgoing"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="direction must be 'incoming' or 'outgoing'",
        )
    try:
        return await service.list_requests_for_team_inbox(
            team_id, principal, direction=direction, status_filter=status_filter
        )
    except TeamNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/requests/{request_id}/fulfill",
    response_model=TaskRequestResponse,
    status_code=status.HTTP_200_OK,
)
async def fulfill_request(
    request_id: UUID,
    payload: FulfillRequestPayload,
    principal: PrincipalDep,
    service: TaskServiceDep,
) -> TaskRequestResponse:
    try:
        return await service.fulfill_request(request_id, payload, principal)
    except TaskRequestNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except TaskRequestAlreadyResolvedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except TaskRequestForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except TaskNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.post(
    "/requests/{request_id}/reject",
    response_model=TaskRequestResponse,
    status_code=status.HTTP_200_OK,
)
async def reject_request(
    request_id: UUID,
    payload: RejectRequestPayload,
    principal: PrincipalDep,
    service: TaskServiceDep,
) -> TaskRequestResponse:
    try:
        return await service.reject_request(request_id, payload, principal)
    except TaskRequestNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except TaskRequestAlreadyResolvedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except TaskRequestForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
