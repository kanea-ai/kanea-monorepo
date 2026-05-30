"""Cross-tenant user management surface.

Four endpoints + four contracts:

* ``GET /api/v1/admin/users`` — paginated, search by email or name.
* ``GET /api/v1/admin/users/{id}`` — identity + per-workspace
  memberships.
* ``POST /api/v1/admin/users/{id}/ban`` — flip the platform-wide
  ToS ban. Refuses self-ban and refuses to ban another superadmin.
* ``POST /api/v1/admin/users/{id}/force-password-reset`` —
  randomises ``password_hash`` and stamps
  ``sessions_invalidated_at``; the response body carries the
  simulated email so the back-office can preview the recovery copy.

The auth-dep level effect of those last two is exercised by
``test_users_auth_gates`` next to this file.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import jwt
import pytest
from fastapi.testclient import TestClient

from app.api.deps import (
    get_admin_user_service,
    get_member_repository,
    get_user_repository,
)
from app.application.admin.users_ports import (
    AdminMembershipRow,
    UserRowWithWorkspaceCount,
)
from app.application.admin.users_schemas import (
    AdminUserDetail,
    AdminUserRow,
    ForcePasswordResetResponse,
)
from app.application.admin.users_service import AdminUserService
from app.application.pagination import Page
from app.core.config import settings
from app.domain.entities import Member, User
from app.domain.enums import MemberRole, MemberType
from app.domain.exceptions import ForbiddenError, InvalidMemberTypeError
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


def _user(user_id: UUID, *, is_superadmin: bool = True, is_banned: bool = False) -> User:
    return User(
        id=user_id,
        email="root@kanea.ai",
        full_name="Root",
        password_hash="h",
        is_superadmin=is_superadmin,
        is_banned=is_banned,
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
def admin_service() -> AsyncMock:
    return AsyncMock(spec=AdminUserService)


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
    admin_service: AsyncMock,
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
    app.dependency_overrides[get_admin_user_service] = lambda: admin_service
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_member_repository, None)
        app.dependency_overrides.pop(get_user_repository, None)
        app.dependency_overrides.pop(get_admin_user_service, None)


@pytest.fixture
def auth_headers(principal_ids: tuple[UUID, UUID, UUID]) -> dict[str, str]:
    member_id, workspace_id, _ = principal_ids
    return _bearer(member_id=member_id, workspace_id=workspace_id)


# ---------- listing ----------


def test_list_users_returns_paginated_rows(
    client: TestClient, admin_service: AsyncMock, auth_headers: dict[str, str]
) -> None:
    row = AdminUserRow(
        id=uuid4(),
        email="alice@kanea.ai",
        full_name="Alice",
        is_superadmin=False,
        is_banned=False,
        sessions_invalidated_at=None,
        created_at=datetime.now(UTC),
        workspace_count=3,
    )
    admin_service.list_users.return_value = Page[AdminUserRow](items=[row], total=1)
    response = client.get("/api/v1/admin/users?name=alice&skip=0&limit=10", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["email"] == "alice@kanea.ai"
    assert body["items"][0]["workspace_count"] == 3
    admin_service.list_users.assert_awaited_once_with(name="alice", skip=0, limit=10)


def test_list_users_requires_superadmin(
    client: TestClient,
    admin_service: AsyncMock,
    users_repo: AsyncMock,
    auth_headers: dict[str, str],
    principal_ids: tuple[UUID, UUID, UUID],
) -> None:
    _, _, user_id = principal_ids
    users_repo.get_by_id.return_value = _user(user_id, is_superadmin=False)
    response = client.get("/api/v1/admin/users", headers=auth_headers)
    assert response.status_code == 403
    admin_service.list_users.assert_not_called()


# ---------- detail ----------


def test_get_user_detail_returns_memberships(
    client: TestClient, admin_service: AsyncMock, auth_headers: dict[str, str]
) -> None:
    target_id = uuid4()
    admin_service.get_user_detail.return_value = AdminUserDetail(
        id=target_id,
        email="alice@kanea.ai",
        full_name="Alice",
        is_superadmin=False,
        is_banned=False,
        sessions_invalidated_at=None,
        created_at=datetime.now(UTC),
        memberships=[],
    )
    response = client.get(f"/api/v1/admin/users/{target_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["id"] == str(target_id)


def test_get_user_detail_unknown_404s(
    client: TestClient, admin_service: AsyncMock, auth_headers: dict[str, str]
) -> None:
    admin_service.get_user_detail.side_effect = InvalidMemberTypeError("user not found")
    response = client.get(f"/api/v1/admin/users/{uuid4()}", headers=auth_headers)
    assert response.status_code == 404


# ---------- ban ----------


def test_ban_user_flips_flag(
    client: TestClient, admin_service: AsyncMock, auth_headers: dict[str, str]
) -> None:
    target_id = uuid4()
    admin_service.set_banned.return_value = AdminUserDetail(
        id=target_id,
        email="bad@actor.io",
        full_name="Bad",
        is_superadmin=False,
        is_banned=True,
        sessions_invalidated_at=None,
        created_at=datetime.now(UTC),
        memberships=[],
    )
    response = client.post(
        f"/api/v1/admin/users/{target_id}/ban",
        json={"is_banned": True},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["is_banned"] is True


def test_ban_self_is_403(
    client: TestClient, admin_service: AsyncMock, auth_headers: dict[str, str]
) -> None:
    admin_service.set_banned.side_effect = ForbiddenError("you cannot ban yourself")
    response = client.post(
        f"/api/v1/admin/users/{uuid4()}/ban",
        json={"is_banned": True},
        headers=auth_headers,
    )
    assert response.status_code == 403


def test_ban_unknown_user_404s(
    client: TestClient, admin_service: AsyncMock, auth_headers: dict[str, str]
) -> None:
    admin_service.set_banned.side_effect = InvalidMemberTypeError("user not found")
    response = client.post(
        f"/api/v1/admin/users/{uuid4()}/ban",
        json={"is_banned": True},
        headers=auth_headers,
    )
    assert response.status_code == 404


# ---------- force password reset ----------


def test_force_reset_returns_simulated_email_and_stamp(
    client: TestClient, admin_service: AsyncMock, auth_headers: dict[str, str]
) -> None:
    target_id = uuid4()
    stamp = datetime.now(UTC)
    admin_service.force_password_reset.return_value = ForcePasswordResetResponse(
        user_id=target_id,
        sessions_invalidated_at=stamp,
        simulated_email="To: alice@kanea.ai\nSubject: [Kanea] Password reset\nBody: ...",
    )
    response = client.post(
        f"/api/v1/admin/users/{target_id}/force-password-reset",
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == str(target_id)
    assert "Password reset" in body["simulated_email"]


# ---------- service-level guards ----------


@pytest.fixture
def repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def hasher() -> MagicMock:
    """PasswordHasher.hash is sync — MagicMock not AsyncMock."""
    h = MagicMock()
    h.hash.return_value = "hashed-placeholder"
    return h


@pytest.fixture
def service(repo: AsyncMock, hasher: MagicMock) -> AdminUserService:
    return AdminUserService(users=repo, hasher=hasher)


async def test_service_set_banned_refuses_self(service: AdminUserService, repo: AsyncMock) -> None:
    me_id = uuid4()
    repo.get_user.return_value = _user(me_id, is_superadmin=True)
    from app.application.admin.users_schemas import BanUserRequest

    with pytest.raises(ForbiddenError):
        await service.set_banned(me_id, BanUserRequest(is_banned=True), principal_user_id=me_id)
    repo.set_banned.assert_not_called()


async def test_service_set_banned_refuses_other_superadmin(
    service: AdminUserService, repo: AsyncMock
) -> None:
    other_id = uuid4()
    repo.get_user.return_value = _user(other_id, is_superadmin=True)
    from app.application.admin.users_schemas import BanUserRequest

    with pytest.raises(ForbiddenError):
        await service.set_banned(
            other_id, BanUserRequest(is_banned=True), principal_user_id=uuid4()
        )
    repo.set_banned.assert_not_called()


async def test_service_set_banned_idempotent_noop(
    service: AdminUserService, repo: AsyncMock
) -> None:
    """Re-banning an already-banned user (or unbanning an already-active
    one) is a no-op — the DB write is skipped so the audit trail doesn't
    double-stamp the action."""
    target_id = uuid4()
    target = _user(target_id, is_superadmin=False, is_banned=True)
    repo.get_user.return_value = target
    repo.list_memberships_for_user.return_value = []
    from app.application.admin.users_schemas import BanUserRequest

    await service.set_banned(target_id, BanUserRequest(is_banned=True), principal_user_id=uuid4())
    repo.set_banned.assert_not_called()


async def test_service_force_reset_writes_random_hash_and_stamp(
    service: AdminUserService, repo: AsyncMock, hasher: MagicMock
) -> None:
    target_id = uuid4()
    repo.get_user.return_value = _user(target_id, is_superadmin=False)
    out = await service.force_password_reset(target_id, principal_user_id=uuid4())
    assert isinstance(out.sessions_invalidated_at, datetime)
    repo.force_reset.assert_awaited_once()
    call = repo.force_reset.await_args
    assert call.args == (target_id,)
    assert call.kwargs["new_password_hash"] == "hashed-placeholder"  # pragma: allowlist secret
    # And the hasher was given a non-empty placeholder.
    hasher.hash.assert_called_once()
    raw = hasher.hash.call_args.args[0]
    assert isinstance(raw, str) and len(raw) > 16


# Keep the dataclass imports referenced so ruff doesn't strip them —
# they're exercised indirectly through the AsyncMock-spec'd service.
_ = UserRowWithWorkspaceCount
_ = AdminMembershipRow
