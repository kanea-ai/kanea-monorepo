from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_invite_service
from app.application.auth.schemas import TokenResponse
from app.application.tenants.schemas import (
    InviteCreateResponse,
    InvitePreviewResponse,
)
from app.core.config import settings
from app.domain.enums import MemberRole, MemberType
from app.domain.exceptions import (
    ForbiddenError,
    InviteAlreadyAcceptedError,
    InviteExpiredError,
    InviteNotFoundError,
)
from app.infrastructure.security.tokens import JwtSettings, JwtTokenService
from app.main import app


@pytest.fixture
def invite_service() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def jwt_service() -> JwtTokenService:
    return JwtTokenService(
        JwtSettings(
            secret=settings.jwt_secret,
            algorithm=settings.jwt_algorithm,
            human_ttl_seconds=settings.jwt_human_ttl_seconds,
            agent_ttl_seconds=settings.jwt_agent_ttl_seconds,
            issuer=settings.jwt_issuer,
        )
    )


def _bearer(role: MemberRole, jwt_service: JwtTokenService) -> dict[str, str]:
    """Forge a JWT carrying the requested role. Same secret as the api so
    get_current_principal verifies it; same shape as a real token."""
    # `datetime.utcnow().timestamp()` is a footgun — `.timestamp()` on a
    # naive datetime treats it as local time, so on any non-UTC host the
    # timestamps shift by the local offset and the token reads as expired.
    # Always go through tz-aware UTC.
    now = datetime.now(UTC)
    payload = {
        "iss": settings.jwt_issuer,
        "sub": str(uuid4()),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=1)).timestamp()),
        "workspace_id": str(uuid4()),
        "type": MemberType.HUMAN.value,
        "priority": 1 if role is MemberRole.WORKSPACE_OWNER else 5,
        "role": role.value,
        "scope": "human",
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client(invite_service: AsyncMock) -> Iterator[TestClient]:
    app.dependency_overrides[get_invite_service] = lambda: invite_service
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


# ---------- POST /tenants/invites ----------


def test_create_invite_owner_returns_201(
    client: TestClient, invite_service: AsyncMock, jwt_service: JwtTokenService
) -> None:
    workspace_id = uuid4()
    invite_service.create_invite.return_value = InviteCreateResponse(
        id=uuid4(),
        workspace_id=workspace_id,
        email="bob@kanea.ai",
        role=MemberRole.WORKSPACE_MEMBER,
        expires_at=datetime.utcnow() + timedelta(days=7),
        accept_url="https://app.kanea.ai/invite/the-token",
        token="the-token",
    )

    response = client.post(
        "/api/v1/tenants/invites",
        json={"email": "bob@kanea.ai", "role": "WORKSPACE_MEMBER"},
        headers=_bearer(MemberRole.WORKSPACE_OWNER, jwt_service),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "bob@kanea.ai"
    assert body["accept_url"].endswith("/invite/the-token")
    assert body["token"] == "the-token"


def test_create_invite_member_returns_403(client: TestClient, jwt_service: JwtTokenService) -> None:
    response = client.post(
        "/api/v1/tenants/invites",
        json={"email": "bob@kanea.ai", "role": "WORKSPACE_MEMBER"},
        headers=_bearer(MemberRole.WORKSPACE_MEMBER, jwt_service),
    )
    # WorkspaceAdminDep blocks before the service is ever called.
    assert response.status_code == 403
    assert "owner or admin" in response.json()["detail"]


def test_create_invite_unauthenticated_returns_401_or_403(client: TestClient) -> None:
    response = client.post(
        "/api/v1/tenants/invites",
        json={"email": "bob@kanea.ai", "role": "WORKSPACE_MEMBER"},
    )
    # FastAPI's HTTPBearer with auto_error=True returns 403 when the
    # header is entirely missing.
    assert response.status_code in (401, 403)


def test_create_invite_owner_role_returns_403(
    client: TestClient, invite_service: AsyncMock, jwt_service: JwtTokenService
) -> None:
    invite_service.create_invite.side_effect = ForbiddenError(
        "OWNER role cannot be granted via invite"
    )
    response = client.post(
        "/api/v1/tenants/invites",
        json={"email": "bob@kanea.ai", "role": "WORKSPACE_OWNER"},
        headers=_bearer(MemberRole.WORKSPACE_OWNER, jwt_service),
    )
    assert response.status_code == 403


# ---------- GET /tenants/invites/{token} ----------


def test_get_invite_preview_returns_workspace_info(
    client: TestClient, invite_service: AsyncMock
) -> None:
    invite_service.get_invite_preview.return_value = InvitePreviewResponse(
        workspace_name="Acme",
        email="bob@kanea.ai",
        role=MemberRole.WORKSPACE_MEMBER,
        expires_at=datetime.utcnow() + timedelta(days=3),
    )
    # Anonymous — no Authorization header.
    response = client.get("/api/v1/tenants/invites/the-token")
    assert response.status_code == 200
    body = response.json()
    assert body["workspace_name"] == "Acme"
    assert body["email"] == "bob@kanea.ai"


def test_get_invite_preview_404_for_unknown_token(
    client: TestClient, invite_service: AsyncMock
) -> None:
    invite_service.get_invite_preview.side_effect = InviteNotFoundError("not found")
    response = client.get("/api/v1/tenants/invites/nope")
    assert response.status_code == 404


def test_get_invite_preview_410_when_expired(client: TestClient, invite_service: AsyncMock) -> None:
    invite_service.get_invite_preview.side_effect = InviteExpiredError("expired")
    response = client.get("/api/v1/tenants/invites/old")
    assert response.status_code == 410


def test_get_invite_preview_409_when_already_accepted(
    client: TestClient, invite_service: AsyncMock
) -> None:
    invite_service.get_invite_preview.side_effect = InviteAlreadyAcceptedError("used")
    response = client.get("/api/v1/tenants/invites/used")
    assert response.status_code == 409


# ---------- POST /tenants/invites/{token}/accept ----------


def test_accept_invite_returns_201_with_token(
    client: TestClient, invite_service: AsyncMock
) -> None:
    invite_service.accept_invite.return_value = TokenResponse(
        access_token="new-jwt", expires_in=3600
    )
    response = client.post(
        "/api/v1/tenants/invites/the-token/accept",
        json={"full_name": "Bob", "password": "abcdefgh"},  # pragma: allowlist secret
    )
    assert response.status_code == 201
    assert response.json()["access_token"] == "new-jwt"


def test_accept_invite_validation_short_password_returns_422(client: TestClient) -> None:
    response = client.post(
        "/api/v1/tenants/invites/the-token/accept",
        json={"full_name": "Bob", "password": "short"},  # pragma: allowlist secret
    )
    assert response.status_code == 422


# ---------- GET /tenants/members ----------


def test_list_members_passes_query_filters(
    client: TestClient, invite_service: AsyncMock, jwt_service: JwtTokenService
) -> None:
    """Router must build a MemberFilters from the query string and
    pass it to the service alongside the principal."""
    from app.application.tenants.schemas import MemberFilters

    invite_service.list_workspace_members.return_value = []
    team_id = uuid4()
    project_id = uuid4()
    response = client.get(
        f"/api/v1/tenants/members?name=al&role=WORKSPACE_MEMBER"
        f"&team_id={team_id}&project_id={project_id}&humans_only=true",
        headers=_bearer(MemberRole.WORKSPACE_OWNER, jwt_service),
    )
    assert response.status_code == 200
    invite_service.list_workspace_members.assert_awaited_once()
    _principal_arg, filters_arg = invite_service.list_workspace_members.await_args.args
    assert isinstance(filters_arg, MemberFilters)
    assert filters_arg.name == "al"
    assert filters_arg.role is MemberRole.WORKSPACE_MEMBER
    assert filters_arg.team_id == team_id
    assert filters_arg.project_id == project_id
    assert filters_arg.humans_only is True


# ---------- GET /tenants/members/{id} ----------


def test_get_member_returns_member(
    client: TestClient, invite_service: AsyncMock, jwt_service: JwtTokenService
) -> None:
    from tests.auth.factories import make_human

    target = make_human()
    invite_service.get_member.return_value = target
    response = client.get(
        f"/api/v1/tenants/members/{target.id}",
        headers=_bearer(MemberRole.WORKSPACE_MEMBER, jwt_service),
    )
    assert response.status_code == 200
    assert response.json()["id"] == str(target.id)


def test_get_member_404_when_not_found(
    client: TestClient, invite_service: AsyncMock, jwt_service: JwtTokenService
) -> None:
    from app.domain.exceptions import InvalidMemberTypeError

    invite_service.get_member.side_effect = InvalidMemberTypeError("nope")
    response = client.get(
        f"/api/v1/tenants/members/{uuid4()}",
        headers=_bearer(MemberRole.WORKSPACE_OWNER, jwt_service),
    )
    assert response.status_code == 404


def test_get_member_403_when_visibility_denied(
    client: TestClient, invite_service: AsyncMock, jwt_service: JwtTokenService
) -> None:
    invite_service.get_member.side_effect = ForbiddenError("nope")
    response = client.get(
        f"/api/v1/tenants/members/{uuid4()}",
        headers=_bearer(MemberRole.WORKSPACE_MEMBER, jwt_service),
    )
    assert response.status_code == 403


# ---------- PATCH /tenants/members/{id} ----------


def test_update_member_profile_owner_can_rename(
    client: TestClient, invite_service: AsyncMock, jwt_service: JwtTokenService
) -> None:
    from tests.auth.factories import make_human

    target = make_human(name="Renamed")
    invite_service.update_member_profile.return_value = target
    response = client.patch(
        f"/api/v1/tenants/members/{target.id}",
        json={"name": "Renamed"},
        headers=_bearer(MemberRole.WORKSPACE_OWNER, jwt_service),
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Renamed"


def test_update_member_profile_member_returns_403(
    client: TestClient, jwt_service: JwtTokenService
) -> None:
    response = client.patch(
        f"/api/v1/tenants/members/{uuid4()}",
        json={"name": "Renamed"},
        headers=_bearer(MemberRole.WORKSPACE_MEMBER, jwt_service),
    )
    assert response.status_code == 403
