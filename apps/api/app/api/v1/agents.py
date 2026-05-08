from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status

from app.api.deps import AgentServiceDep, PrincipalDep
from app.application.agents.schemas import (
    AgentDetailResponse,
    AgentResponse,
    CreateAgentRequest,
    CreateAgentResponse,
    UpdateAgentRequest,
)
from app.domain.exceptions import (
    AgentHasCreatedTasksError,
    AgentNotFoundError,
)

router = APIRouter(prefix="/agents", tags=["agents"])


@router.post(
    "",
    response_model=CreateAgentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_agent(
    payload: CreateAgentRequest,
    principal: PrincipalDep,
    service: AgentServiceDep,
) -> CreateAgentResponse:
    """Provision a new agent in the requester's workspace and return its
    API key in plaintext. The key is bcrypt-hashed on persist and cannot
    be recovered — the caller must show / copy it immediately."""
    return await service.create_agent(payload, principal)


@router.get(
    "",
    response_model=list[AgentResponse],
    status_code=status.HTTP_200_OK,
)
async def list_agents(
    principal: PrincipalDep,
    service: AgentServiceDep,
) -> list[AgentResponse]:
    return await service.list_agents(principal)


@router.get(
    "/{agent_id}",
    response_model=AgentDetailResponse,
    status_code=status.HTTP_200_OK,
)
async def get_agent_detail(
    agent_id: UUID,
    principal: PrincipalDep,
    service: AgentServiceDep,
) -> AgentDetailResponse:
    """Detail view: agent fields + computed stats (assigned, completed,
    avg resolution time, accuracy from ratings, last activity, tokens).
    Tenant-scoped — agents in other workspaces 404 with the same shape
    as truly-missing so cross-tenant probing reveals nothing."""
    try:
        return await service.get_agent_detail(agent_id, principal)
    except AgentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch(
    "/{agent_id}",
    response_model=AgentResponse,
    status_code=status.HTTP_200_OK,
)
async def update_agent(
    agent_id: UUID,
    payload: UpdateAgentRequest,
    principal: PrincipalDep,
    service: AgentServiceDep,
) -> AgentResponse:
    """Partial update: name / priority / model. id is immutable."""
    try:
        return await service.update_agent(agent_id, payload, principal)
    except AgentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete(
    "/{agent_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_agent(
    agent_id: UUID,
    principal: PrincipalDep,
    service: AgentServiceDep,
) -> Response:
    """Hard delete. 409 if the agent created tasks (those would be
    orphaned via the FK RESTRICT on tasks.created_by_id)."""
    try:
        await service.delete_agent(agent_id, principal)
    except AgentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AgentHasCreatedTasksError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
