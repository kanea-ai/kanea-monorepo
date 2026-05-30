"""Superadmin gate — the boundary between every standard workspace
user (including OWNERs) and the platform back-office.

The ``/api/v1/admin/*`` surface is protected by ``get_current_superadmin``.
Three contract points:

1. No bearer / malformed bearer → 401 Unauthorized.
2. Valid bearer, but the underlying User row's ``is_superadmin`` is
   False → 403 Forbidden. Workspace OWNER role is NOT enough — this is
   a platform-level flag, not a workspace-level one.
3. Valid bearer AND ``is_superadmin = True`` → 200 (the dummy
   ``/admin/health`` endpoint exists purely to exercise the gate).

The flag itself is set out-of-band (CLI script ``scripts.make_superadmin``)
so there is NO API path that can elevate a user to superadmin.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_member_repository, get_user_repository
from app.core.config import settings
from app.domain.entities import Member, User
from app.domain.enums import MemberRole, MemberType
from app.main import app


def _bearer(*, member_id: str | None = None, workspace_id: str | None = None) -> dict[str, str]:
    """Forge a workspace-scoped JWT. The superadmin gate doesn't care
    which workspace it was minted for — the only signal is whether the
    underlying User row has ``is_superadmin=True``."""
    now = datetime.now(UTC)
    payload = {
        "iss": settings.jwt_issuer,
        "sub": member_id or str(uuid4()),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=1)).timestamp()),
        "workspace_id": workspace_id or str(uuid4()),
        "type": "HUMAN",
        "priority": 1,
        # Even a WORKSPACE_OWNER role is not enough — the gate is the
        # platform-level flag, not the workspace role.
        "role": MemberRole.WORKSPACE_OWNER.value,
        "scope": "human",
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return {"Authorization": f"Bearer {token}"}


def _member(*, member_id, workspace_id, user_id) -> Member:
    return Member(
        id=member_id,
        workspace_id=workspace_id,
        type=MemberType.HUMAN,
        name="X",
        priority=1,
        role=MemberRole.WORKSPACE_OWNER,
        user_id=user_id,
    )


def _user(*, user_id, email: str = "x@x.com", is_superadmin: bool = False) -> User:
    return User(
        id=user_id,
        email=email,
        full_name="X",
        password_hash="h",
        is_superadmin=is_superadmin,
    )


@pytest.fixture
def members_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def users_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def client(members_repo: AsyncMock, users_repo: AsyncMock) -> Iterator[TestClient]:
    app.dependency_overrides[get_member_repository] = lambda: members_repo
    app.dependency_overrides[get_user_repository] = lambda: users_repo
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_member_repository, None)
        app.dependency_overrides.pop(get_user_repository, None)


def test_health_no_bearer_is_rejected(client: TestClient) -> None:
    """No Authorization header → FastAPI's HTTPBearer (auto_error=True)
    rejects with 403 before we ever reach our dep — matches the rest
    of the app's auth surface. Either 401 or 403 is "unauthenticated"
    from the client's POV; we assert the route refused."""
    response = client.get("/api/v1/admin/health")
    assert response.status_code in (401, 403)


def test_health_malformed_bearer_is_401(client: TestClient) -> None:
    """Malformed JWT — our ``_decode_principal`` rejects with a
    distinct 401 + ``WWW-Authenticate: Bearer`` header so a client
    that DID send credentials gets the proper "retry with a fresh
    token" signal."""
    response = client.get(
        "/api/v1/admin/health", headers={"Authorization": "Bearer not-a-real-jwt"}
    )
    assert response.status_code == 401
    assert response.headers.get("www-authenticate", "").lower().startswith("bearer")


def test_health_non_superadmin_is_403(
    client: TestClient, members_repo: AsyncMock, users_repo: AsyncMock
) -> None:
    """Even with a valid OWNER JWT, the gate refuses if the user row's
    ``is_superadmin`` is False. The Owner role is for workspaces, not
    the platform; this is the design's safety belt."""
    member_id = uuid4()
    workspace_id = uuid4()
    user_id = uuid4()
    members_repo.get_by_id.return_value = _member(
        member_id=member_id, workspace_id=workspace_id, user_id=user_id
    )
    users_repo.get_by_id.return_value = _user(user_id=user_id, is_superadmin=False)

    response = client.get(
        "/api/v1/admin/health",
        headers=_bearer(member_id=str(member_id), workspace_id=str(workspace_id)),
    )
    assert response.status_code == 403


def test_health_superadmin_is_200(
    client: TestClient, members_repo: AsyncMock, users_repo: AsyncMock
) -> None:
    member_id = uuid4()
    workspace_id = uuid4()
    user_id = uuid4()
    members_repo.get_by_id.return_value = _member(
        member_id=member_id, workspace_id=workspace_id, user_id=user_id
    )
    users_repo.get_by_id.return_value = _user(user_id=user_id, is_superadmin=True)

    response = client.get(
        "/api/v1/admin/health",
        headers=_bearer(member_id=str(member_id), workspace_id=str(workspace_id)),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    # The endpoint also returns the resolved superadmin's email so the
    # caller can confirm which identity passed the gate.
    assert body["email"] == "x@x.com"


def test_health_member_row_missing_is_401(client: TestClient, members_repo: AsyncMock) -> None:
    """A stale token whose member row has been deleted should 401, not
    fall through to 403 — the principal can't be resolved at all."""
    members_repo.get_by_id.return_value = None
    response = client.get("/api/v1/admin/health", headers=_bearer())
    assert response.status_code == 401


def test_health_user_row_missing_is_401(
    client: TestClient, members_repo: AsyncMock, users_repo: AsyncMock
) -> None:
    """Same shape if the underlying global User row is gone — the JWT
    was valid but the identity behind it doesn't exist anymore."""
    member_id = uuid4()
    workspace_id = uuid4()
    user_id = uuid4()
    members_repo.get_by_id.return_value = _member(
        member_id=member_id, workspace_id=workspace_id, user_id=user_id
    )
    users_repo.get_by_id.return_value = None
    response = client.get(
        "/api/v1/admin/health",
        headers=_bearer(member_id=str(member_id), workspace_id=str(workspace_id)),
    )
    assert response.status_code == 401
