"""Auth-dep level tests for the workspace-scoped suspension gate.

Contract:
- A workspace-scoped JWT for a suspended member is rejected with 403
  on every workspace route.
- The same User can hold a separate workspace-scoped JWT for a
  *different* workspace where they're not suspended; that token works.
- The cross-workspace ``RawPrincipalDep`` route (/auth/switch-workspace)
  remains reachable so a suspended user can move to another workspace.
- A select-token (scope=='select') skips the suspension gate — it's
  not workspace-bound; the gate applies to the JWT the picker exchanges
  it for.
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
    get_workspace_repository,
)
from app.core.config import settings
from app.domain.entities import Member, Workspace
from app.domain.enums import MemberRole, MemberType
from app.main import app


def _workspace(workspace_id: UUID, *, suspended_at=None) -> Workspace:
    now = datetime.now(UTC)
    return Workspace(
        id=workspace_id,
        name="X",
        slug="x",
        task_prefix="X",
        next_task_seq=1,
        created_at=now,
        updated_at=now,
        suspended_at=suspended_at,
    )


def _bearer(*, member_id: UUID, workspace_id: UUID, scope: str = "human") -> dict[str, str]:
    """Forge a workspace-scoped JWT — sub=member_id, plus the workspace
    binding the auth dep validates."""
    now = datetime.now(UTC)
    payload = {
        "iss": settings.jwt_issuer,
        "sub": str(member_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=1)).timestamp()),
        "workspace_id": str(workspace_id),
        "type": "HUMAN",
        "priority": 1,
        "role": "WORKSPACE_USER",
        "scope": scope,
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return {"Authorization": f"Bearer {token}"}


def _member(member_id: UUID, workspace_id: UUID, *, suspended: bool) -> Member:
    now = datetime.now(UTC)
    return Member(
        id=member_id,
        workspace_id=workspace_id,
        type=MemberType.HUMAN,
        name="Alice",
        email="a@example.com",
        priority=3,
        role=MemberRole.WORKSPACE_USER,
        is_suspended=suspended,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def members_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def workspaces_repo() -> AsyncMock:
    """Default to an active workspace; tests for the workspace-suspension
    gate override ``get_by_id`` to return a suspended row."""
    r = AsyncMock()
    r.get_by_id.return_value = None  # tests set this per case
    return r


@pytest.fixture
def client(members_repo: AsyncMock, workspaces_repo: AsyncMock) -> Iterator[TestClient]:
    """Stub the member + workspace repos (used by the suspension gates)
    and the team service so the route resolves quickly. The team
    listing route is a convenient probe — it sits behind PrincipalDep
    so both gates run.

    Removes the autouse ``_bypass_suspension_gate_by_default`` override
    so the real ``get_current_principal`` path runs, which is the whole
    point of these tests.
    """
    app.dependency_overrides.pop(get_current_principal, None)
    app.dependency_overrides[get_member_repository] = lambda: members_repo
    app.dependency_overrides[get_workspace_repository] = lambda: workspaces_repo
    team_service_mock = AsyncMock()
    # /teams now returns Page[TeamResponse] — wrap the empty list so
    # the route's response_model validation passes.
    from app.application.pagination import Page
    from app.application.teams.schemas import TeamResponse

    team_service_mock.list_for_workspace.return_value = Page[TeamResponse](items=[], total=0)
    app.dependency_overrides[get_team_service] = lambda: team_service_mock
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


# ---------- 403 for suspended membership ----------


def test_suspended_membership_gets_403_on_workspace_route(
    client: TestClient, members_repo: AsyncMock
) -> None:
    """The auth dep loads the member, sees is_suspended=True, and
    rejects the request before reaching the route handler."""
    member_id = uuid4()
    workspace_id = uuid4()
    members_repo.get_by_id.return_value = _member(member_id, workspace_id, suspended=True)
    response = client.get(
        "/api/v1/teams",
        headers=_bearer(member_id=member_id, workspace_id=workspace_id),
    )
    assert response.status_code == 403
    assert "suspend" in response.json()["detail"].lower()


# ---------- active membership in a DIFFERENT workspace works ----------


def test_unsuspended_membership_passes(
    client: TestClient, members_repo: AsyncMock, workspaces_repo: AsyncMock
) -> None:
    """A separate JWT for another workspace where the member is NOT
    suspended AND the workspace is active must work — the suspension is
    per-membership / per-workspace, not per-user."""
    member_id = uuid4()
    workspace_id = uuid4()
    members_repo.get_by_id.return_value = _member(member_id, workspace_id, suspended=False)
    workspaces_repo.get_by_id.return_value = _workspace(workspace_id)
    response = client.get(
        "/api/v1/teams",
        headers=_bearer(member_id=member_id, workspace_id=workspace_id),
    )
    assert response.status_code == 200


# ---------- 403 for workspace-wide suspension ----------


def test_workspace_suspended_returns_403(
    client: TestClient, members_repo: AsyncMock, workspaces_repo: AsyncMock
) -> None:
    """A superadmin flipped ``workspaces.suspended_at`` from the back-
    office; every workspace-scoped JWT for that workspace bounces with
    403, even for members who themselves are not personally suspended.
    The detail string distinguishes this from a per-member suspension
    so the UI can render the right copy."""
    member_id = uuid4()
    workspace_id = uuid4()
    members_repo.get_by_id.return_value = _member(member_id, workspace_id, suspended=False)
    workspaces_repo.get_by_id.return_value = _workspace(
        workspace_id, suspended_at=datetime.now(UTC)
    )
    response = client.get(
        "/api/v1/teams",
        headers=_bearer(member_id=member_id, workspace_id=workspace_id),
    )
    assert response.status_code == 403
    assert "workspace suspended" in response.json()["detail"].lower()


# ---------- cross-tenant membership rejected ----------


def test_member_from_different_workspace_rejected(
    client: TestClient, members_repo: AsyncMock
) -> None:
    """If the JWT's workspace_id doesn't match the member row's
    workspace_id, the token is treated as invalid (401) — same shape
    we use for tampered tokens."""
    member_id = uuid4()
    other_workspace = uuid4()
    members_repo.get_by_id.return_value = _member(member_id, other_workspace, suspended=False)
    response = client.get(
        "/api/v1/teams",
        headers=_bearer(member_id=member_id, workspace_id=uuid4()),
    )
    assert response.status_code == 401


# ---------- deleted member ----------


def test_deleted_member_rejected_401(client: TestClient, members_repo: AsyncMock) -> None:
    """Member row no longer exists — old token is invalidated."""
    members_repo.get_by_id.return_value = None
    response = client.get(
        "/api/v1/teams",
        headers=_bearer(member_id=uuid4(), workspace_id=uuid4()),
    )
    assert response.status_code == 401


# ---------- /auth/switch-workspace bypass ----------


def test_switch_workspace_reachable_for_suspended_member(
    client: TestClient, members_repo: AsyncMock
) -> None:
    """The /auth/switch-workspace endpoint uses RawPrincipalDep so a
    member who is currently suspended in their active workspace can
    still hit it to escape into another. We don't fully exercise the
    auth service here — just that the suspension gate doesn't fire."""
    from app.api.deps import get_auth_service

    auth_service_mock = AsyncMock()
    auth_service_mock.switch_workspace.return_value = type(
        "T", (), {"access_token": "new.jwt", "token_type": "bearer", "expires_in": 3600}
    )()
    app.dependency_overrides[get_auth_service] = lambda: auth_service_mock

    # Even though members_repo would mark the principal as suspended,
    # the switch endpoint never asks the gate — RawPrincipalDep skips
    # the DB lookup entirely.
    members_repo.get_by_id.return_value = _member(uuid4(), uuid4(), suspended=True)

    response = client.post(
        "/api/v1/auth/switch-workspace",
        json={"workspace_id": str(uuid4())},
        headers=_bearer(member_id=uuid4(), workspace_id=uuid4()),
    )
    # The mocked service returns a TokenResponse-like; FastAPI will
    # serialise via the route's response_model. We just confirm the
    # auth-gate didn't fire (i.e. status is NOT 403).
    assert response.status_code != 403
