"""AgentService API-key endpoints — issue / list / revoke.

Service-layer behaviour. The router-layer wiring lives in
``test_agent_api_keys_router.py``; the security primitives live in
``test_agent_api_keys_primitives.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.application.agents.schemas import IssueAgentApiKeyRequest
from app.application.agents.service import AgentService
from app.application.tasks.schemas import Principal
from app.domain.entities import AgentApiKey
from app.domain.enums import MemberRole, MemberType
from app.domain.exceptions import (
    AgentApiKeyNotFoundError,
    AgentNotFoundError,
    ForbiddenError,
)
from tests.auth.factories import make_agent

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


# ---------- issue ----------


async def test_issue_api_key_returns_plaintext_once(
    service: AgentService,
    members_for_listing: AsyncMock,
    api_keys: AsyncMock,
) -> None:
    """Issue mints a fresh key, persists the hash, returns plaintext
    exactly once with a fingerprint (prefix + last4)."""
    p = _principal()
    agent = make_agent(workspace_id=p.workspace_id)
    members_for_listing.get_by_id.return_value = agent
    api_keys.create.side_effect = lambda k: k

    response = await service.issue_api_key(agent.id, IssueAgentApiKeyRequest(label="ci-runner"), p)

    assert response.api_key.startswith(f"kna_{_ENV_TAG}_")
    assert response.prefix == f"kna_{_ENV_TAG}_"
    assert len(response.last4) == 4
    assert response.label == "ci-runner"

    api_keys.create.assert_awaited_once()
    persisted = api_keys.create.await_args.args[0]
    assert persisted.member_id == agent.id
    assert persisted.created_by_member_id == p.member_id
    # Plaintext never lands in the secret_hash column.
    assert response.api_key not in persisted.secret_hash


async def test_issue_rejected_for_non_admin(
    service: AgentService, members_for_listing: AsyncMock, api_keys: AsyncMock
) -> None:
    p = _principal(role=MemberRole.WORKSPACE_USER)
    members_for_listing.get_by_id.return_value = make_agent(workspace_id=p.workspace_id)
    with pytest.raises(ForbiddenError):
        await service.issue_api_key(uuid4(), IssueAgentApiKeyRequest(), p)
    api_keys.create.assert_not_called()


async def test_issue_404s_for_cross_workspace_agent(
    service: AgentService, members_for_listing: AsyncMock
) -> None:
    p = _principal()
    members_for_listing.get_by_id.return_value = make_agent(workspace_id=uuid4())
    with pytest.raises(AgentNotFoundError):
        await service.issue_api_key(uuid4(), IssueAgentApiKeyRequest(), p)


# ---------- list ----------


async def test_list_returns_metadata_only(
    service: AgentService,
    members_for_listing: AsyncMock,
    api_keys: AsyncMock,
) -> None:
    p = _principal()
    agent = make_agent(workspace_id=p.workspace_id)
    members_for_listing.get_by_id.return_value = agent
    api_keys.list_for_member.return_value = [
        AgentApiKey(
            id=uuid4(),
            member_id=agent.id,
            secret_hash="x" * 64,
            prefix="kna_dev_",
            last4="aBcD",
            created_by_member_id=p.member_id,
            created_at=datetime.now(UTC),
        ),
    ]
    rows = await service.list_api_keys(agent.id, p)
    assert len(rows) == 1
    # The response schema only carries metadata — no plaintext, no hash.
    serialised = rows[0].model_dump()
    assert "api_key" not in serialised
    assert "secret_hash" not in serialised
    assert serialised["last4"] == "aBcD"


async def test_list_rejected_for_non_admin(
    service: AgentService, members_for_listing: AsyncMock, api_keys: AsyncMock
) -> None:
    p = _principal(role=MemberRole.WORKSPACE_USER)
    members_for_listing.get_by_id.return_value = make_agent(workspace_id=p.workspace_id)
    with pytest.raises(ForbiddenError):
        await service.list_api_keys(uuid4(), p)
    api_keys.list_for_member.assert_not_called()


# ---------- revoke ----------


async def test_revoke_soft_revokes_via_repo(
    service: AgentService,
    members_for_listing: AsyncMock,
    api_keys: AsyncMock,
) -> None:
    p = _principal()
    agent = make_agent(workspace_id=p.workspace_id)
    members_for_listing.get_by_id.return_value = agent
    key_id = uuid4()
    api_keys.get_by_id.return_value = AgentApiKey(
        id=key_id,
        member_id=agent.id,
        secret_hash="x" * 64,
        prefix="kna_dev_",
        last4="aBcD",
        created_by_member_id=p.member_id,
        created_at=datetime.now(UTC),
    )
    await service.revoke_api_key(agent.id, key_id, p)
    api_keys.revoke.assert_awaited_once()
    assert api_keys.revoke.await_args.args[0] == key_id


async def test_revoke_404s_for_cross_agent_key(
    service: AgentService,
    members_for_listing: AsyncMock,
    api_keys: AsyncMock,
) -> None:
    """A key id belonging to a different agent in the same workspace
    must NOT be revokable through the wrong path — surfaces as 404 so
    cross-agent probing is indistinguishable from a non-existent key."""
    p = _principal()
    agent = make_agent(workspace_id=p.workspace_id)
    members_for_listing.get_by_id.return_value = agent
    other_member_id = uuid4()
    api_keys.get_by_id.return_value = AgentApiKey(
        id=uuid4(),
        member_id=other_member_id,
        secret_hash="x" * 64,
        prefix="kna_dev_",
        last4="aBcD",
        created_by_member_id=p.member_id,
        created_at=datetime.now(UTC),
    )
    with pytest.raises(AgentApiKeyNotFoundError):
        await service.revoke_api_key(agent.id, uuid4(), p)
    api_keys.revoke.assert_not_called()


async def test_revoke_rejected_for_non_admin(
    service: AgentService, members_for_listing: AsyncMock, api_keys: AsyncMock
) -> None:
    p = _principal(role=MemberRole.WORKSPACE_USER)
    members_for_listing.get_by_id.return_value = make_agent(workspace_id=p.workspace_id)
    with pytest.raises(ForbiddenError):
        await service.revoke_api_key(uuid4(), uuid4(), p)
    api_keys.revoke.assert_not_called()
