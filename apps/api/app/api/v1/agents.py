from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import AgentServiceDep, PrincipalDep
from app.application.agents.schemas import (
    AgentResponse,
    CreateAgentRequest,
    CreateAgentResponse,
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
    be recovered — the caller must show / copy it immediately. JWT is
    required (PrincipalDep) so workspace_id is taken from the token."""
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
