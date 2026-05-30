"""Back-office dashboard metrics surface.

Contract:

* ``GET /api/v1/admin/metrics`` returns a single object with three
  top-line counters (active workspaces / registered users / total
  tokens used) and a recent-signups list (last 7 days, capped at 50).
* The endpoint is gated by ``SuperadminDep`` like every other
  ``/admin/*`` route.
* The service composes its response from exactly two repo calls
  (summary aggregates + recent signups) — no N+1 over workspaces or
  users.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import jwt
import pytest
from fastapi.testclient import TestClient

from app.api.deps import (
    get_admin_metrics_service,
    get_member_repository,
    get_user_repository,
)
from app.application.admin.metrics_ports import PlatformSummaryAggregates
from app.application.admin.metrics_service import AdminMetricsService
from app.core.config import settings
from app.domain.entities import Member, User
from app.domain.enums import MemberRole, MemberType
from app.main import app


def _bearer(*, member_id: UUID, workspace_id: UUID) -> dict[str, str]:
    now = datetime.now(UTC)
    payload = {
        "iss": settings.jwt_issuer,
        "sub": str(member_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=1)).timestamp()),
        "workspace_id": str(workspace_id),
        "type": "HUMAN",
        "priority": 1,
        "role": MemberRole.WORKSPACE_OWNER.value,
        "scope": "human",
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return {"Authorization": f"Bearer {token}"}


def _user(user_id: UUID, *, is_superadmin: bool = True) -> User:
    return User(
        id=user_id,
        email="root@kanea.ai",
        full_name="Root",
        password_hash="h",
        is_superadmin=is_superadmin,
    )


def _member(*, member_id, workspace_id, user_id) -> Member:
    return Member(
        id=member_id,
        workspace_id=workspace_id,
        type=MemberType.HUMAN,
        name="Root",
        priority=1,
        role=MemberRole.WORKSPACE_OWNER,
        user_id=user_id,
    )


# ---------- fixtures ----------


@pytest.fixture
def metrics_service() -> AsyncMock:
    return AsyncMock(spec=AdminMetricsService)


@pytest.fixture
def members_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def users_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def principal_ids() -> tuple[UUID, UUID, UUID]:
    return uuid4(), uuid4(), uuid4()


@pytest.fixture
def client(
    metrics_service: AsyncMock,
    members_repo: AsyncMock,
    users_repo: AsyncMock,
    principal_ids: tuple[UUID, UUID, UUID],
) -> Iterator[TestClient]:
    member_id, workspace_id, user_id = principal_ids
    members_repo.get_by_id.return_value = _member(
        member_id=member_id, workspace_id=workspace_id, user_id=user_id
    )
    users_repo.get_by_id.return_value = _user(user_id, is_superadmin=True)
    app.dependency_overrides[get_member_repository] = lambda: members_repo
    app.dependency_overrides[get_user_repository] = lambda: users_repo
    app.dependency_overrides[get_admin_metrics_service] = lambda: metrics_service
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_member_repository, None)
        app.dependency_overrides.pop(get_user_repository, None)
        app.dependency_overrides.pop(get_admin_metrics_service, None)


@pytest.fixture
def auth_headers(principal_ids: tuple[UUID, UUID, UUID]) -> dict[str, str]:
    member_id, workspace_id, _ = principal_ids
    return _bearer(member_id=member_id, workspace_id=workspace_id)


# ---------- route ----------


def test_metrics_returns_summary_shape(
    client: TestClient, metrics_service: AsyncMock, auth_headers: dict[str, str]
) -> None:
    from app.application.admin.metrics_schemas import (
        PlatformMetricsResponse,
        RecentSignup,
    )

    signup_id = uuid4()
    metrics_service.get_summary.return_value = PlatformMetricsResponse(
        total_active_workspaces=12,
        total_registered_users=345,
        total_tokens_used=987_654,
        recent_signups=[
            RecentSignup(
                id=signup_id,
                email="newbie@example.com",
                full_name="New Bie",
                created_at=datetime.now(UTC),
            )
        ],
    )
    response = client.get("/api/v1/admin/metrics", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total_active_workspaces"] == 12
    assert body["total_registered_users"] == 345
    assert body["total_tokens_used"] == 987_654
    assert body["recent_signups"][0]["id"] == str(signup_id)


def test_metrics_requires_superadmin(
    client: TestClient,
    metrics_service: AsyncMock,
    users_repo: AsyncMock,
    auth_headers: dict[str, str],
    principal_ids: tuple[UUID, UUID, UUID],
) -> None:
    _, _, user_id = principal_ids
    users_repo.get_by_id.return_value = _user(user_id, is_superadmin=False)
    response = client.get("/api/v1/admin/metrics", headers=auth_headers)
    assert response.status_code == 403
    metrics_service.get_summary.assert_not_called()


# ---------- service-level ----------


async def test_service_composes_summary_from_two_repo_calls() -> None:
    """The service hits the repo exactly twice — once for the
    summary aggregates and once for the recent signups list. That's
    the contract for the dashboard's single-round-trip rendering."""
    repo = AsyncMock()
    repo.get_summary.return_value = PlatformSummaryAggregates(
        total_active_workspaces=3,
        total_registered_users=42,
        total_tokens_used=1_234,
    )
    repo.list_recent_signups.return_value = [
        User(
            id=uuid4(),
            email="a@example.com",
            full_name="Alice",
            password_hash="h",
            created_at=datetime.now(UTC),
        )
    ]
    service = AdminMetricsService(metrics=repo)
    out = await service.get_summary()
    assert out.total_active_workspaces == 3
    assert out.total_registered_users == 42
    assert out.total_tokens_used == 1_234
    assert len(out.recent_signups) == 1
    repo.get_summary.assert_awaited_once()
    repo.list_recent_signups.assert_awaited_once()


async def test_service_caps_recent_signups_list_at_configured_limit() -> None:
    """The service passes its configured ``recent_limit`` to the
    repo; tightening it later is a one-field change."""
    repo = AsyncMock()
    repo.get_summary.return_value = PlatformSummaryAggregates(
        total_active_workspaces=0, total_registered_users=0, total_tokens_used=0
    )
    repo.list_recent_signups.return_value = []
    service = AdminMetricsService(metrics=repo, recent_window_days=14, recent_limit=10)
    await service.get_summary()
    repo.list_recent_signups.assert_awaited_once_with(since_days=14, limit=10)
