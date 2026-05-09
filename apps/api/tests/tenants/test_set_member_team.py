"""Tests for InviteService.set_member_team and the route guards.

Contract:
- Workspace OWNER / ADMIN can assign a member to a team and set their
  team_role.
- MEMBER role is rejected (ForbiddenError -> 403 at the route).
- Setting team_id without team_role (or vice versa) is rejected.
- Cross-tenant member id surfaces as 404.
- Cross-tenant team id surfaces as 404.
- POST /api/v1/teams now requires WorkspaceAdminDep.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient

from app.api.deps import (
    InviteServiceDep,
    get_team_service,
)
from app.application.tasks.schemas import Principal
from app.application.tenants.schemas import SetMemberTeamRequest
from app.application.tenants.service import InviteService
from app.core.config import settings
from app.domain.entities import Member, Team
from app.domain.enums import MemberRole, MemberType, TeamRole
from app.domain.exceptions import ForbiddenError, InvalidMemberTypeError
from app.main import app


def _principal(*, role: MemberRole = MemberRole.OWNER, workspace_id=None) -> Principal:
    return Principal(
        member_id=uuid4(),
        workspace_id=workspace_id or uuid4(),
        type=MemberType.HUMAN,
        priority=1,
        scope="human",
        role=role,
    )


def _member(workspace_id) -> Member:
    return Member(
        id=uuid4(),
        workspace_id=workspace_id,
        type=MemberType.HUMAN,
        name="Alice",
        email="a@example.com",
        priority=3,
        role=MemberRole.MEMBER,
    )


def _team(workspace_id) -> Team:
    now = datetime.now(UTC)
    return Team(
        id=uuid4(),
        workspace_id=workspace_id,
        name="Backend",
        created_at=now,
        updated_at=now,
    )


# ---------- service ----------


@pytest.fixture
def invites_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def members_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def workspaces_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def teams_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def auth_members() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(
    invites_repo: AsyncMock,
    members_repo: AsyncMock,
    workspaces_repo: AsyncMock,
    teams_repo: AsyncMock,
    auth_members: AsyncMock,
) -> InviteService:
    return InviteService(
        invites=invites_repo,
        members=members_repo,
        workspaces=workspaces_repo,
        auth_members=auth_members,
        credentials=AsyncMock(),
        hasher=AsyncMock(),
        tokens=AsyncMock(),
        accept_url_base="http://example",
        teams=teams_repo,
    )


async def test_member_role_is_forbidden(service: InviteService) -> None:
    p = _principal(role=MemberRole.MEMBER)
    with pytest.raises(ForbiddenError):
        await service.set_member_team(
            uuid4(), SetMemberTeamRequest(team_id=uuid4(), team_role=TeamRole.LEAD), p
        )


async def test_team_id_without_role_rejected(service: InviteService) -> None:
    p = _principal()
    with pytest.raises(InvalidMemberTypeError):
        # Pydantic accepts the raw dict; missing team_role surfaces at the
        # service level so the API client gets a clean 4xx.
        await service.set_member_team(
            uuid4(),
            SetMemberTeamRequest.model_validate({"team_id": str(uuid4())}),
            p,
        )


async def test_role_without_team_id_rejected(service: InviteService) -> None:
    p = _principal()
    with pytest.raises(InvalidMemberTypeError):
        await service.set_member_team(uuid4(), SetMemberTeamRequest(team_role=TeamRole.LEAD), p)


async def test_cross_tenant_member_404s(service: InviteService, members_repo: AsyncMock) -> None:
    p = _principal()
    members_repo.get_by_id.return_value = _member(uuid4())  # other workspace
    with pytest.raises(InvalidMemberTypeError):
        await service.set_member_team(
            uuid4(),
            SetMemberTeamRequest(team_id=uuid4(), team_role=TeamRole.MEMBER),
            p,
        )


async def test_cross_tenant_team_404s(
    service: InviteService,
    members_repo: AsyncMock,
    teams_repo: AsyncMock,
) -> None:
    p = _principal()
    members_repo.get_by_id.return_value = _member(p.workspace_id)
    teams_repo.get_by_id.return_value = _team(uuid4())  # other workspace
    with pytest.raises(InvalidMemberTypeError):
        await service.set_member_team(
            uuid4(),
            SetMemberTeamRequest(team_id=uuid4(), team_role=TeamRole.MEMBER),
            p,
        )


async def test_happy_path_assigns_member(
    service: InviteService,
    members_repo: AsyncMock,
    teams_repo: AsyncMock,
) -> None:
    p = _principal(role=MemberRole.ADMIN)
    target = _member(p.workspace_id)
    team = _team(p.workspace_id)
    members_repo.get_by_id.return_value = target
    teams_repo.get_by_id.return_value = team
    members_repo.set_team.side_effect = lambda _id, **kw: target

    await service.set_member_team(
        target.id,
        SetMemberTeamRequest(team_id=team.id, team_role=TeamRole.LEAD),
        p,
    )

    members_repo.set_team.assert_awaited_once_with(
        target.id, team_id=team.id, team_role=TeamRole.LEAD
    )


async def test_clear_team_assignment_when_team_id_null(
    service: InviteService, members_repo: AsyncMock
) -> None:
    p = _principal(role=MemberRole.ADMIN)
    target = _member(p.workspace_id)
    members_repo.get_by_id.return_value = target
    members_repo.set_team.side_effect = lambda _id, **kw: target

    await service.set_member_team(target.id, SetMemberTeamRequest(), p)

    members_repo.set_team.assert_awaited_once_with(target.id, team_id=None, team_role=None)


# ---------- POST /api/v1/teams now requires admin ----------


@pytest.fixture
def team_service_mock() -> AsyncMock:
    return AsyncMock()


def _bearer(role: str) -> dict[str, str]:
    """Forge a JWT with the given workspace role."""
    from datetime import timedelta

    now = datetime.now(UTC)
    payload = {
        "iss": settings.jwt_issuer,
        "sub": str(uuid4()),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=1)).timestamp()),
        "workspace_id": str(uuid4()),
        "type": "HUMAN",
        "priority": 1,
        "role": role,
        "scope": "human",
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client(team_service_mock: AsyncMock) -> Iterator[TestClient]:
    app.dependency_overrides[get_team_service] = lambda: team_service_mock
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_post_teams_rejects_member_role(client: TestClient, team_service_mock: AsyncMock) -> None:
    response = client.post(
        "/api/v1/teams",
        json={"name": "Backend"},
        headers=_bearer("MEMBER"),
    )
    assert response.status_code == 403
    team_service_mock.create.assert_not_called()


def test_post_teams_accepts_admin(client: TestClient, team_service_mock: AsyncMock) -> None:
    team_service_mock.create.return_value = type(
        "T",
        (),
        {
            "id": uuid4(),
            "workspace_id": uuid4(),
            "name": "Backend",
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        },
    )()
    response = client.post(
        "/api/v1/teams",
        json={"name": "Backend"},
        headers=_bearer("ADMIN"),
    )
    assert response.status_code == 201
    team_service_mock.create.assert_awaited_once()


def test_set_member_team_route_rejects_member_role(client: TestClient) -> None:
    """The PATCH endpoint sits behind WorkspaceAdminDep — a non-admin
    JWT is rejected before reaching the service."""
    response = client.patch(
        f"/api/v1/tenants/members/{uuid4()}/team",
        json={"team_id": str(uuid4()), "team_role": "LEAD"},
        headers=_bearer("MEMBER"),
    )
    assert response.status_code == 403


def test_set_member_team_route_404s_for_unknown_member(client: TestClient) -> None:
    """Admin JWT but cross-tenant member id → service raises
    InvalidMemberTypeError → router maps to 404."""
    invite_service_mock = AsyncMock()
    invite_service_mock.set_member_team.side_effect = InvalidMemberTypeError("member not found")
    # Override invite service dep too.
    from app.api.deps import get_invite_service

    app.dependency_overrides[get_invite_service] = lambda: invite_service_mock
    try:
        response = client.patch(
            f"/api/v1/tenants/members/{uuid4()}/team",
            json={"team_id": str(uuid4()), "team_role": "LEAD"},
            headers=_bearer("ADMIN"),
        )
        assert response.status_code == 404
    finally:
        app.dependency_overrides.pop(get_invite_service, None)


# Hint to suppress unused fixture warning: InviteServiceDep is referenced
# implicitly via app.dependency_overrides[get_invite_service]. The import
# documents the dep we're substituting.
_ = InviteServiceDep
