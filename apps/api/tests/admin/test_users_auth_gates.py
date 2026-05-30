"""Auth-dep level tests for the two new global User gates.

Contract:

* ``users.is_banned = True`` → ``get_current_principal`` returns
  403 ``account banned`` on every workspace route.
* JWT ``iat`` < ``users.sessions_invalidated_at`` → ``get_current_principal``
  returns 401. Used by the force-password-reset flow to invalidate
  outstanding sessions without a token blacklist.
* Fresh JWT issued AFTER the invalidation stamp passes again, so the
  user can sign back in after running the recovery flow.
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
    get_current_principal,
    get_member_repository,
    get_team_service,
    get_user_repository,
    get_workspace_repository,
)
from app.core.config import settings
from app.domain.entities import Member, User, Workspace
from app.domain.enums import MemberRole, MemberType
from app.main import app


def _bearer(*, member_id: UUID, workspace_id: UUID, iat: datetime | None = None) -> dict[str, str]:
    now = iat or datetime.now(UTC)
    payload = {
        "iss": settings.jwt_issuer,
        "sub": str(member_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=1)).timestamp()),
        "workspace_id": str(workspace_id),
        "type": "HUMAN",
        "priority": 3,
        "role": MemberRole.WORKSPACE_USER.value,
        "scope": "human",
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return {"Authorization": f"Bearer {token}"}


def _member(member_id: UUID, workspace_id: UUID, *, user_id: UUID) -> Member:
    now = datetime.now(UTC)
    return Member(
        id=member_id,
        workspace_id=workspace_id,
        type=MemberType.HUMAN,
        name="Alice",
        email="a@example.com",
        priority=3,
        role=MemberRole.WORKSPACE_USER,
        user_id=user_id,
        is_suspended=False,
        created_at=now,
        updated_at=now,
    )


def _workspace(workspace_id: UUID) -> Workspace:
    now = datetime.now(UTC)
    return Workspace(
        id=workspace_id,
        name="X",
        slug="x",
        task_prefix="X",
        next_task_seq=1,
        created_at=now,
        updated_at=now,
    )


def _user(
    user_id: UUID,
    *,
    is_banned: bool = False,
    sessions_invalidated_at: datetime | None = None,
) -> User:
    return User(
        id=user_id,
        email="a@example.com",
        full_name="Alice",
        password_hash="h",
        is_banned=is_banned,
        sessions_invalidated_at=sessions_invalidated_at,
    )


@pytest.fixture
def members_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def workspaces_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def users_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def client(
    members_repo: AsyncMock,
    workspaces_repo: AsyncMock,
    users_repo: AsyncMock,
) -> Iterator[TestClient]:
    """Real ``get_current_principal`` path. Override the four DB-backed
    repos it depends on, and stub the team service so the listing
    route resolves to an empty page."""
    app.dependency_overrides.pop(get_current_principal, None)
    app.dependency_overrides[get_member_repository] = lambda: members_repo
    app.dependency_overrides[get_workspace_repository] = lambda: workspaces_repo
    app.dependency_overrides[get_user_repository] = lambda: users_repo
    team_service_mock = AsyncMock()
    from app.application.pagination import Page
    from app.application.teams.schemas import TeamResponse

    team_service_mock.list_for_workspace.return_value = Page[TeamResponse](items=[], total=0)
    app.dependency_overrides[get_team_service] = lambda: team_service_mock
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_banned_user_gets_403(
    client: TestClient,
    members_repo: AsyncMock,
    workspaces_repo: AsyncMock,
    users_repo: AsyncMock,
) -> None:
    member_id = uuid4()
    workspace_id = uuid4()
    user_id = uuid4()
    members_repo.get_by_id.return_value = _member(member_id, workspace_id, user_id=user_id)
    workspaces_repo.get_by_id.return_value = _workspace(workspace_id)
    users_repo.get_by_id.return_value = _user(user_id, is_banned=True)

    response = client.get(
        "/api/v1/teams",
        headers=_bearer(member_id=member_id, workspace_id=workspace_id),
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "account banned"


def test_pre_invalidation_jwt_gets_401(
    client: TestClient,
    members_repo: AsyncMock,
    workspaces_repo: AsyncMock,
    users_repo: AsyncMock,
) -> None:
    """JWT minted BEFORE ``sessions_invalidated_at`` is rejected with
    401 — the back-office force-reset takes effect immediately on the
    next request."""
    member_id = uuid4()
    workspace_id = uuid4()
    user_id = uuid4()
    members_repo.get_by_id.return_value = _member(member_id, workspace_id, user_id=user_id)
    workspaces_repo.get_by_id.return_value = _workspace(workspace_id)
    # Force-reset stamp is "now"; JWT iat sits 60 seconds in the past.
    now = datetime.now(UTC)
    users_repo.get_by_id.return_value = _user(user_id, sessions_invalidated_at=now)

    response = client.get(
        "/api/v1/teams",
        headers=_bearer(
            member_id=member_id,
            workspace_id=workspace_id,
            iat=now - timedelta(seconds=60),
        ),
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "session invalidated"


def test_post_invalidation_jwt_passes(
    client: TestClient,
    members_repo: AsyncMock,
    workspaces_repo: AsyncMock,
    users_repo: AsyncMock,
) -> None:
    """The user signed back in AFTER the force-reset stamp; the fresh
    JWT carries an ``iat`` that beats the invalidation watermark and
    the gate lets it through."""
    member_id = uuid4()
    workspace_id = uuid4()
    user_id = uuid4()
    members_repo.get_by_id.return_value = _member(member_id, workspace_id, user_id=user_id)
    workspaces_repo.get_by_id.return_value = _workspace(workspace_id)
    now = datetime.now(UTC)
    users_repo.get_by_id.return_value = _user(
        user_id, sessions_invalidated_at=now - timedelta(minutes=5)
    )

    response = client.get(
        "/api/v1/teams",
        headers=_bearer(member_id=member_id, workspace_id=workspace_id, iat=now),
    )
    assert response.status_code == 200
