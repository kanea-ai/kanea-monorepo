"""Service-level coverage for the agent detail/update/delete operations
added in Phase 5.5. Tenant isolation is the headline contract: all four
new operations must 404 when the agent_id resolves outside the
principal's workspace, and same shape as truly-missing so cross-tenant
probing reveals nothing."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.application.agents.schemas import (
    CreateAgentRequest,
    UpdateAgentRequest,
)
from app.application.agents.service import AgentService
from app.application.tasks.schemas import Principal
from app.domain.entities import AgentStats, Member
from app.domain.enums import MemberRole, MemberType
from app.domain.exceptions import (
    AgentHasCreatedTasksError,
    AgentNotFoundError,
)


def _principal(*, workspace_id=None, member_id=None) -> Principal:
    return Principal(
        member_id=member_id or uuid4(),
        workspace_id=workspace_id or uuid4(),
        type=MemberType.HUMAN,
        priority=1,
        scope="human",
        role=MemberRole.WORKSPACE_OWNER,
    )


def _agent(*, agent_id=None, workspace_id=None, name="bot", priority=5, model=None) -> Member:
    return Member(
        id=agent_id or uuid4(),
        workspace_id=workspace_id or uuid4(),
        type=MemberType.AGENT,
        name=name,
        priority=priority,
        email=None,
        role=MemberRole.WORKSPACE_MEMBER,
        model=model,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


@pytest.fixture
def members_for_listing() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def auth_members() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def credentials() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def hasher() -> MagicMock:
    h = MagicMock()
    h.hash.side_effect = lambda raw: f"bcrypt${raw}"
    return h


@pytest.fixture
def service(
    members_for_listing: AsyncMock,
    auth_members: AsyncMock,
    credentials: AsyncMock,
    hasher: MagicMock,
) -> AgentService:
    return AgentService(
        members_for_listing=members_for_listing,
        auth_members=auth_members,
        credentials=credentials,
        hasher=hasher,
    )


# ---------- create with model ----------


async def test_create_agent_persists_model_attribute(
    service: AgentService, auth_members: AsyncMock, credentials: AsyncMock
) -> None:
    auth_members.create.side_effect = lambda m: m
    credentials.create.side_effect = lambda c: c
    p = _principal()

    response = await service.create_agent(
        CreateAgentRequest(name="bot", priority=5, model="claude-opus-4-7"), p
    )

    assert response.model == "claude-opus-4-7"
    created = auth_members.create.await_args.args[0]
    assert created.model == "claude-opus-4-7"


# ---------- get_agent_detail ----------


async def test_detail_returns_agent_plus_stats(
    service: AgentService, members_for_listing: AsyncMock
) -> None:
    p = _principal()
    agent = _agent(workspace_id=p.workspace_id, model="claude-opus-4-7")
    members_for_listing.get_by_id.return_value = agent
    members_for_listing.compute_agent_stats.return_value = AgentStats(
        assigned_count=3,
        completed_count=12,
        avg_resolution_seconds=1800.0,
        accuracy_percent=87.5,
        last_activity_at=datetime.utcnow(),
        total_tokens_used=42_000,
    )

    detail = await service.get_agent_detail(agent.id, p)

    assert detail.id == agent.id
    assert detail.model == "claude-opus-4-7"
    assert detail.stats.assigned_count == 3
    assert detail.stats.completed_count == 12
    assert detail.stats.accuracy_percent == 87.5
    assert detail.stats.total_tokens_used == 42_000


async def test_detail_404s_for_other_workspace(
    service: AgentService, members_for_listing: AsyncMock
) -> None:
    """Agent exists, but in a different workspace — must look like
    'not found' to the caller."""
    p = _principal()
    members_for_listing.get_by_id.return_value = _agent(workspace_id=uuid4())
    with pytest.raises(AgentNotFoundError):
        await service.get_agent_detail(uuid4(), p)


async def test_detail_404s_for_human_member(
    service: AgentService, members_for_listing: AsyncMock
) -> None:
    """The id resolves to a HUMAN member, not an agent. Same workspace
    even, but type guard fails."""
    p = _principal()
    members_for_listing.get_by_id.return_value = Member(
        id=uuid4(),
        workspace_id=p.workspace_id,
        type=MemberType.HUMAN,
        name="alice",
        priority=1,
        email="alice@example.com",
        role=MemberRole.WORKSPACE_OWNER,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    with pytest.raises(AgentNotFoundError):
        await service.get_agent_detail(uuid4(), p)


# ---------- update_agent ----------


async def test_update_partial_fields(service: AgentService, members_for_listing: AsyncMock) -> None:
    p = _principal()
    agent = _agent(workspace_id=p.workspace_id, name="old", priority=5, model="old-model")
    members_for_listing.get_by_id.return_value = agent
    members_for_listing.update.return_value = _agent(
        agent_id=agent.id,
        workspace_id=p.workspace_id,
        name="new",
        priority=7,
        model="new-model",
    )

    response = await service.update_agent(
        agent.id,
        UpdateAgentRequest(name="new", priority=7, model="new-model"),
        p,
    )

    assert response.name == "new"
    assert response.priority == 7
    assert response.model == "new-model"
    members_for_listing.update.assert_awaited_once_with(
        agent.id, name="new", priority=7, model="new-model", clear_model=False
    )


async def test_update_omitted_fields_are_left_alone(
    service: AgentService, members_for_listing: AsyncMock
) -> None:
    """Empty body is a 200 no-op (members_for_listing.update still called
    but with all None and clear_model=False)."""
    p = _principal()
    agent = _agent(workspace_id=p.workspace_id)
    members_for_listing.get_by_id.return_value = agent
    members_for_listing.update.return_value = agent

    await service.update_agent(agent.id, UpdateAgentRequest(), p)

    members_for_listing.update.assert_awaited_once_with(
        agent.id, name=None, priority=None, model=None, clear_model=False
    )


async def test_update_explicit_null_model_clears_it(
    service: AgentService, members_for_listing: AsyncMock
) -> None:
    """Passing `model: null` is distinct from omitting `model` — it
    explicitly clears the field. The service distinguishes via Pydantic's
    `model_fields_set`."""
    p = _principal()
    agent = _agent(workspace_id=p.workspace_id, model="some-model")
    members_for_listing.get_by_id.return_value = agent
    members_for_listing.update.return_value = _agent(
        agent_id=agent.id, workspace_id=p.workspace_id, model=None
    )

    payload = UpdateAgentRequest.model_validate({"model": None})
    await service.update_agent(agent.id, payload, p)

    members_for_listing.update.assert_awaited_once()
    kwargs = members_for_listing.update.await_args.kwargs
    assert kwargs["clear_model"] is True


async def test_update_404s_for_other_workspace(
    service: AgentService, members_for_listing: AsyncMock
) -> None:
    p = _principal()
    members_for_listing.get_by_id.return_value = _agent(workspace_id=uuid4())
    with pytest.raises(AgentNotFoundError):
        await service.update_agent(uuid4(), UpdateAgentRequest(name="hax"), p)


# ---------- delete_agent ----------


async def test_delete_agent_with_no_created_tasks_succeeds(
    service: AgentService, members_for_listing: AsyncMock
) -> None:
    p = _principal()
    agent = _agent(workspace_id=p.workspace_id)
    members_for_listing.get_by_id.return_value = agent
    members_for_listing.has_created_tasks.return_value = False

    await service.delete_agent(agent.id, p)

    members_for_listing.delete.assert_awaited_once_with(agent.id)


async def test_delete_refused_when_agent_has_created_tasks(
    service: AgentService, members_for_listing: AsyncMock
) -> None:
    p = _principal()
    agent = _agent(workspace_id=p.workspace_id)
    members_for_listing.get_by_id.return_value = agent
    members_for_listing.has_created_tasks.return_value = True

    with pytest.raises(AgentHasCreatedTasksError):
        await service.delete_agent(agent.id, p)

    members_for_listing.delete.assert_not_called()


async def test_delete_404s_for_other_workspace(
    service: AgentService, members_for_listing: AsyncMock
) -> None:
    """Cross-tenant delete attempts must 404, not 403 — same shape as
    truly-missing so a probe can't even confirm the agent exists in
    another workspace."""
    p = _principal()
    members_for_listing.get_by_id.return_value = _agent(workspace_id=uuid4())
    with pytest.raises(AgentNotFoundError):
        await service.delete_agent(uuid4(), p)
    members_for_listing.delete.assert_not_called()
