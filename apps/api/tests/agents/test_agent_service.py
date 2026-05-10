from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.application.agents.schemas import CreateAgentRequest
from app.application.agents.service import AgentService
from app.application.tasks.schemas import Principal
from app.domain.enums import MemberRole, MemberType


def _principal(*, workspace_id=None, member_id=None) -> Principal:
    return Principal(
        member_id=member_id or uuid4(),
        workspace_id=workspace_id or uuid4(),
        type=MemberType.HUMAN,
        priority=1,
        scope="human",
        role=MemberRole.WORKSPACE_OWNER,
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


async def test_create_agent_returns_plaintext_key_once(
    service: AgentService,
    auth_members: AsyncMock,
    credentials: AsyncMock,
    hasher: MagicMock,
) -> None:
    auth_members.create.side_effect = lambda m: m
    credentials.create.side_effect = lambda c: c
    p = _principal()

    response = await service.create_agent(CreateAgentRequest(name="researcher-bot", priority=5), p)

    # Plaintext key returned to caller (32 bytes urlsafe → 43 chars).
    assert response.api_key
    assert len(response.api_key) >= 40
    # Member created as AGENT in the requester's workspace, no email.
    auth_members.create.assert_awaited_once()
    created_member = auth_members.create.await_args.args[0]
    assert created_member.workspace_id == p.workspace_id
    assert created_member.type is MemberType.AGENT
    assert created_member.email is None
    assert created_member.priority == 5
    assert created_member.name == "researcher-bot"
    # Credentials carry the bcrypted secret, not the plaintext.
    credentials.create.assert_awaited_once()
    creds = credentials.create.await_args.args[0]
    assert creds.member_id == created_member.id
    assert creds.password_hash is None
    assert creds.agent_secret_hash == f"bcrypt${response.api_key}"


async def test_list_agents_filters_to_principal_workspace(
    service: AgentService, members_for_listing: AsyncMock
) -> None:
    p = _principal()
    members_for_listing.list_agents_for_workspace.return_value = []
    await service.list_agents(p)
    members_for_listing.list_agents_for_workspace.assert_awaited_once_with(p.workspace_id)


async def test_two_creates_yield_distinct_keys(
    service: AgentService, auth_members: AsyncMock, credentials: AsyncMock
) -> None:
    """Sanity: each call mints a fresh secret. If the same key were
    returned twice, the second agent would reuse the first's credentials."""
    auth_members.create.side_effect = lambda m: m
    credentials.create.side_effect = lambda c: c
    p = _principal()

    a = await service.create_agent(CreateAgentRequest(name="bot-1"), p)
    b = await service.create_agent(CreateAgentRequest(name="bot-2"), p)
    assert a.api_key != b.api_key
    assert a.id != b.id
