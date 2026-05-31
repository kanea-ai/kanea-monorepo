from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.application.agents.schemas import CreateAgentRequest
from app.application.agents.service import AgentService
from app.application.tasks.schemas import Principal
from app.domain.enums import MemberRole, MemberType
from app.domain.exceptions import ForbiddenError

# Constant inputs for the key-format / pepper tests below. The pepper is
# arbitrary — the assertions only care that minted keys are valid format
# strings, not what their hashes look like.
_ENV_TAG = "dev"
_PEPPER = "test-pepper"


def _principal(
    *,
    workspace_id=None,
    member_id=None,
    role: MemberRole = MemberRole.WORKSPACE_OWNER,
) -> Principal:
    return Principal(
        member_id=member_id or uuid4(),
        workspace_id=workspace_id or uuid4(),
        type=MemberType.HUMAN,
        priority=1,
        scope="human",
        role=role,
    )


@pytest.fixture
def members_for_listing() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def auth_members() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def api_keys() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(
    members_for_listing: AsyncMock,
    auth_members: AsyncMock,
    api_keys: AsyncMock,
) -> AgentService:
    return AgentService(
        members_for_listing=members_for_listing,
        auth_members=auth_members,
        api_keys=api_keys,
        env_tag=_ENV_TAG,
        pepper=_PEPPER,
    )


async def test_create_agent_returns_plaintext_key_once(
    service: AgentService,
    auth_members: AsyncMock,
    api_keys: AsyncMock,
) -> None:
    """Plaintext appears in the response exactly once; only the HMAC
    digest is persisted to ``agent_api_keys``. Verifies that no legacy
    ``credentials`` write happens on the agent path."""
    auth_members.create.side_effect = lambda m: m
    api_keys.create.side_effect = lambda k: k
    p = _principal()

    response = await service.create_agent(CreateAgentRequest(name="researcher-bot", priority=5), p)

    assert response.api_key.startswith(f"kna_{_ENV_TAG}_")
    # 32-byte CSPRNG → 43 base64url chars. Total length is prefix + body.
    assert len(response.api_key) >= len(f"kna_{_ENV_TAG}_") + 40

    auth_members.create.assert_awaited_once()
    created_member = auth_members.create.await_args.args[0]
    assert created_member.workspace_id == p.workspace_id
    assert created_member.type is MemberType.AGENT
    assert created_member.email is None
    assert created_member.priority == 5
    assert created_member.name == "researcher-bot"

    api_keys.create.assert_awaited_once()
    persisted = api_keys.create.await_args.args[0]
    assert persisted.member_id == created_member.id
    # The plaintext is NEVER persisted — neither in secret_hash nor anywhere.
    assert persisted.secret_hash != response.api_key
    assert response.api_key not in persisted.secret_hash
    assert persisted.prefix == f"kna_{_ENV_TAG}_"
    assert len(persisted.last4) == 4


async def test_create_agent_rejects_non_admin_principal(
    service: AgentService, auth_members: AsyncMock, api_keys: AsyncMock
) -> None:
    """Belt-and-braces: the route layer enforces WorkspaceAdminDep, but
    the service re-asserts so agents can't self-provision via a leaked
    USER-role JWT even if the route wiring drifts."""
    p = _principal(role=MemberRole.WORKSPACE_USER)
    with pytest.raises(ForbiddenError):
        await service.create_agent(CreateAgentRequest(name="bot"), p)
    auth_members.create.assert_not_called()
    api_keys.create.assert_not_called()


async def test_list_agents_filters_to_principal_workspace(
    service: AgentService, members_for_listing: AsyncMock
) -> None:
    p = _principal()
    members_for_listing.list_agents_for_workspace.return_value = []
    await service.list_agents(p)
    members_for_listing.list_agents_for_workspace.assert_awaited_once_with(p.workspace_id)


async def test_two_creates_yield_distinct_keys(
    service: AgentService, auth_members: AsyncMock, api_keys: AsyncMock
) -> None:
    """Sanity: each call mints a fresh secret. If the same key were
    returned twice, the second agent would inherit the first's auth."""
    auth_members.create.side_effect = lambda m: m
    api_keys.create.side_effect = lambda k: k
    p = _principal()

    a = await service.create_agent(CreateAgentRequest(name="bot-1"), p)
    b = await service.create_agent(CreateAgentRequest(name="bot-2"), p)
    assert a.api_key != b.api_key
    assert a.id != b.id
