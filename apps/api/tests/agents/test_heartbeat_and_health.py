"""TDD coverage for the agent heartbeat / health-status feature.

Contract:

- `POST /api/v1/agents/me/heartbeat` is agent-only — humans get 403,
  tokens with scope != "agent" are rejected before the handler runs.
- AgentService.heartbeat() stamps `members.last_seen_at` for the
  calling agent member.
- AgentService.get_agent_detail() exposes `last_seen_at` and a
  derived `health_status` ∈ {ONLINE, IDLE, STALE}:
    * ONLINE  : last_seen_at within 5 min of now
    * IDLE    : within 1 hour
    * STALE   : >1 hour OR never (None)
- Auth-side: when an agent exchanges its key for a JWT
  (POST /api/v1/auth/agent-token), last_seen_at is stamped — agents
  that never call the explicit heartbeat still get a freshness signal
  on every reconnect.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_agent_service
from app.application.agents.service import AgentService, derive_health_status
from app.application.tasks.schemas import Principal
from app.core.config import settings
from app.domain.entities import AgentStats, Member
from app.domain.enums import MemberRole, MemberType
from app.main import app


def _principal(*, scope: str = "human", workspace_id=None, member_id=None) -> Principal:
    return Principal(
        member_id=member_id or uuid4(),
        workspace_id=workspace_id or uuid4(),
        type=MemberType.HUMAN if scope == "human" else MemberType.AGENT,
        priority=1 if scope == "human" else 5,
        scope=scope,
        role=MemberRole.WORKSPACE_OWNER if scope == "human" else MemberRole.WORKSPACE_USER,
    )


def _agent(*, workspace_id=None, last_seen_at=None) -> Member:
    return Member(
        id=uuid4(),
        workspace_id=workspace_id or uuid4(),
        type=MemberType.AGENT,
        name="bot",
        priority=5,
        email=None,
        role=MemberRole.WORKSPACE_USER,
        model="claude-opus-4-7",
        last_seen_at=last_seen_at,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


# ---------- derive_health_status (pure function) ----------


def test_health_online_when_seen_within_5_minutes() -> None:
    assert derive_health_status(datetime.now(UTC) - timedelta(minutes=2)) == "ONLINE"


def test_health_idle_when_seen_within_an_hour() -> None:
    assert derive_health_status(datetime.now(UTC) - timedelta(minutes=30)) == "IDLE"


def test_health_stale_when_seen_long_ago() -> None:
    assert derive_health_status(datetime.now(UTC) - timedelta(hours=4)) == "STALE"


def test_health_stale_when_never_seen() -> None:
    assert derive_health_status(None) == "STALE"


# ---------- AgentService.heartbeat ----------


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
    return MagicMock()


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


async def test_heartbeat_stamps_last_seen_for_calling_agent(
    service: AgentService, members_for_listing: AsyncMock
) -> None:
    """An agent posting to /me/heartbeat updates its own row — the
    repo is asked to set last_seen_at for the principal's member_id."""
    p = _principal(scope="agent")
    await service.heartbeat(p)
    members_for_listing.heartbeat.assert_awaited_once_with(p.member_id)


# ---------- AgentService.get_agent_detail health_status ----------


async def test_detail_exposes_health_status_and_last_seen(
    service: AgentService, members_for_listing: AsyncMock
) -> None:
    p = _principal()
    seen = datetime.now(UTC) - timedelta(minutes=3)
    agent = _agent(workspace_id=p.workspace_id, last_seen_at=seen)
    members_for_listing.get_by_id.return_value = agent
    members_for_listing.compute_agent_stats.return_value = AgentStats(
        assigned_count=0,
        completed_count=0,
        avg_resolution_seconds=None,
        accuracy_percent=None,
        last_activity_at=None,
        total_tokens_used=0,
    )

    detail = await service.get_agent_detail(agent.id, p)

    assert detail.last_seen_at == seen
    assert detail.health_status == "ONLINE"


async def test_detail_health_stale_when_agent_never_seen(
    service: AgentService, members_for_listing: AsyncMock
) -> None:
    p = _principal()
    agent = _agent(workspace_id=p.workspace_id, last_seen_at=None)
    members_for_listing.get_by_id.return_value = agent
    members_for_listing.compute_agent_stats.return_value = AgentStats(
        assigned_count=0,
        completed_count=0,
        avg_resolution_seconds=None,
        accuracy_percent=None,
        last_activity_at=None,
        total_tokens_used=0,
    )
    detail = await service.get_agent_detail(agent.id, p)
    assert detail.last_seen_at is None
    assert detail.health_status == "STALE"


# ---------- POST /api/v1/agents/me/heartbeat ----------


@pytest.fixture
def agent_service() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def client(agent_service: AsyncMock) -> Iterator[TestClient]:
    app.dependency_overrides[get_agent_service] = lambda: agent_service
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _bearer(scope: str) -> dict[str, str]:
    """Forge a JWT with the given scope — same secret as the api so
    get_current_principal verifies it."""
    now = datetime.now(UTC)
    payload = {
        "iss": settings.jwt_issuer,
        "sub": str(uuid4()),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=1)).timestamp()),
        "workspace_id": str(uuid4()),
        "type": MemberType.HUMAN.value if scope == "human" else MemberType.AGENT.value,
        "priority": 1 if scope == "human" else 5,
        "role": (
            MemberRole.WORKSPACE_OWNER.value
            if scope == "human"
            else MemberRole.WORKSPACE_USER.value
        ),
        "scope": scope,
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return {"Authorization": f"Bearer {token}"}


def test_heartbeat_endpoint_with_agent_jwt_returns_204(
    client: TestClient, agent_service: AsyncMock
) -> None:
    response = client.post("/api/v1/agents/me/heartbeat", headers=_bearer("agent"))
    assert response.status_code == 204
    agent_service.heartbeat.assert_awaited_once()


def test_heartbeat_endpoint_rejects_human_scope(
    client: TestClient, agent_service: AsyncMock
) -> None:
    """Humans must not be able to spoof an agent heartbeat."""
    response = client.post("/api/v1/agents/me/heartbeat", headers=_bearer("human"))
    assert response.status_code == 403
    agent_service.heartbeat.assert_not_called()


def test_heartbeat_endpoint_unauthenticated_returns_401_or_403(
    client: TestClient,
) -> None:
    response = client.post("/api/v1/agents/me/heartbeat")
    assert response.status_code in (401, 403)
