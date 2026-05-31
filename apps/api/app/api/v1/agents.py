from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status

from app.api.deps import (
    AgentScopeDep,
    AgentServiceDep,
    PrincipalDep,
    WorkspaceAdminDep,
)
from app.application.agents.schemas import (
    AgentApiKeyResponse,
    AgentDetailResponse,
    AgentResponse,
    CreateAgentRequest,
    CreateAgentResponse,
    IssueAgentApiKeyRequest,
    IssueAgentApiKeyResponse,
    UpdateAgentRequest,
)
from app.domain.exceptions import (
    AgentApiKeyNotFoundError,
    AgentHasCreatedTasksError,
    AgentNotFoundError,
    ForbiddenError,
)

router = APIRouter(prefix="/agents", tags=["agents"])


@router.post(
    "",
    response_model=CreateAgentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_agent(
    payload: CreateAgentRequest,
    principal: WorkspaceAdminDep,
    service: AgentServiceDep,
) -> CreateAgentResponse:
    """Provision a new agent in the requester's workspace and mint a
    first API key in the same response. The plaintext is returned
    exactly once — only the HMAC-SHA-256 digest of the key body is
    persisted, so the secret cannot be recovered.

    Gated by ``WorkspaceAdminDep`` (WORKSPACE_OWNER / WORKSPACE_ADMIN).
    """
    try:
        return await service.create_agent(payload, principal)
    except ForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


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


@router.post(
    "/me/heartbeat",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def agent_heartbeat(
    principal: AgentScopeDep,
    service: AgentServiceDep,
) -> Response:
    """Agent-only liveness ping. Stamps members.last_seen_at = now() so
    the workspace UI can show ONLINE/IDLE/STALE for this agent. 403 for
    human callers — only an agent JWT (scope='agent') may report its
    own presence."""
    await service.heartbeat(principal)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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


# ---------------------------------------------------------------------------
# API key management. All three operations are admin-gated (consistency
# with the issuance + revocation security posture). Plaintext is returned
# exactly once on POST; subsequent reads only show prefix + last4.
# ---------------------------------------------------------------------------


@router.post(
    "/{agent_id}/api-keys",
    response_model=IssueAgentApiKeyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def issue_agent_api_key(
    agent_id: UUID,
    payload: IssueAgentApiKeyRequest,
    principal: WorkspaceAdminDep,
    service: AgentServiceDep,
) -> IssueAgentApiKeyResponse:
    """Mint an additional API key for an existing agent. Returns the
    plaintext exactly once; the response shape includes a fingerprint
    (``prefix`` + ``last4``) so the operator has something to label
    locally before discarding the plaintext."""
    try:
        return await service.issue_api_key(agent_id, payload, principal)
    except AgentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.get(
    "/{agent_id}/api-keys",
    response_model=list[AgentApiKeyResponse],
    status_code=status.HTTP_200_OK,
)
async def list_agent_api_keys(
    agent_id: UUID,
    principal: WorkspaceAdminDep,
    service: AgentServiceDep,
) -> list[AgentApiKeyResponse]:
    """Inventory listing — metadata only (no plaintext, no hash).
    Newest-first by ``created_at``. Admin-gated to keep key inventory
    out of casual reconnaissance reach."""
    try:
        return await service.list_api_keys(agent_id, principal)
    except AgentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.delete(
    "/{agent_id}/api-keys/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def revoke_agent_api_key(
    agent_id: UUID,
    key_id: UUID,
    principal: WorkspaceAdminDep,
    service: AgentServiceDep,
) -> Response:
    """Soft-revoke. The next ``/auth/agent-token`` call with this key
    will 401. Idempotent — re-revoking an already-revoked key is a
    no-op 204. Keys belonging to another agent (or to no one) surface
    as 404, the same shape as cross-tenant probing."""
    try:
        await service.revoke_api_key(agent_id, key_id, principal)
    except AgentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AgentApiKeyNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
