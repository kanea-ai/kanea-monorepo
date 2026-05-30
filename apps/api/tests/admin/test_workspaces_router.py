"""Back-office workspace management surface.

Two endpoints + two contracts:

* ``GET /api/v1/admin/workspaces`` — paginated cross-tenant listing
  with per-row aggregated metrics. Search by name OR slug; sort by
  created_at / name / suspended_at. Unknown sort keys fall back to
  ``created_at_desc`` rather than 400-ing.

* ``PATCH /api/v1/admin/workspaces/{id}/suspend`` — soft-suspend
  (sets ``suspended_at`` = now) or restore (clears it). Idempotent
  on both sides. 404 for unknown id; 403 for non-superadmin.
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
    get_admin_workspace_service,
    get_member_repository,
    get_user_repository,
)
from app.application.admin.ports import WorkspaceRowWithMetrics
from app.application.admin.schemas import AdminWorkspaceRow, WorkspaceMetrics
from app.application.admin.service import AdminWorkspaceService
from app.application.pagination import Page
from app.core.config import settings
from app.domain.entities import Member, User, Workspace
from app.domain.enums import MemberRole, MemberType
from app.domain.exceptions import WorkspaceNotFoundError
from app.main import app


def _bearer(*, member_id: UUID, workspace_id: UUID) -> dict[str, str]:
    """Forge a workspace-scoped JWT. ``member_id`` + ``workspace_id``
    must match what the fixtures wire so the cross-tenant guard in
    ``get_current_superadmin`` passes."""
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


def _user(user_id: UUID, *, is_superadmin: bool = True) -> User:
    return User(
        id=user_id,
        email="root@kanea.ai",
        full_name="Root",
        password_hash="h",
        is_superadmin=is_superadmin,
    )


def _workspace(*, workspace_id=None, name="Acme", slug="acme", suspended_at=None) -> Workspace:
    now = datetime.now(UTC)
    return Workspace(
        id=workspace_id or uuid4(),
        name=name,
        slug=slug,
        task_prefix=slug.upper()[:8],
        next_task_seq=1,
        created_at=now,
        updated_at=now,
        suspended_at=suspended_at,
    )


# ---------- fixtures ----------


@pytest.fixture
def admin_service() -> AsyncMock:
    return AsyncMock(spec=AdminWorkspaceService)


@pytest.fixture
def members_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def users_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def principal_ids() -> tuple[UUID, UUID, UUID]:
    """(member_id, workspace_id, user_id) — shared so the JWT
    fixture and the repo fixture line up on the same identity."""
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
    app.dependency_overrides[get_admin_workspace_service] = lambda: admin_service
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_member_repository, None)
        app.dependency_overrides.pop(get_user_repository, None)
        app.dependency_overrides.pop(get_admin_workspace_service, None)


@pytest.fixture
def auth_headers(principal_ids: tuple[UUID, UUID, UUID]) -> dict[str, str]:
    member_id, workspace_id, _ = principal_ids
    return _bearer(member_id=member_id, workspace_id=workspace_id)


# ---------- listing ----------


def test_list_workspaces_returns_page_with_metrics(
    client: TestClient, admin_service: AsyncMock, auth_headers: dict[str, str]
) -> None:
    ws = _workspace(name="Acme", slug="acme")
    admin_service.list_workspaces.return_value = Page[AdminWorkspaceRow](
        items=[
            AdminWorkspaceRow(
                id=ws.id,
                name=ws.name,
                slug=ws.slug,
                task_prefix=ws.task_prefix,
                suspended_at=ws.suspended_at,
                created_at=ws.created_at,
                updated_at=ws.updated_at,
                metrics=WorkspaceMetrics(total_users=12, total_tasks=345, total_tokens_used=67_890),
            )
        ],
        total=1,
    )

    response = client.get("/api/v1/admin/workspaces", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["slug"] == "acme"
    assert item["metrics"] == {
        "total_users": 12,
        "total_tasks": 345,
        "total_tokens_used": 67_890,
    }


def test_list_workspaces_forwards_filters(
    client: TestClient, admin_service: AsyncMock, auth_headers: dict[str, str]
) -> None:
    admin_service.list_workspaces.return_value = Page[AdminWorkspaceRow](items=[], total=0)
    client.get(
        "/api/v1/admin/workspaces?name=acme&sort=name_asc&skip=10&limit=5", headers=auth_headers
    )
    admin_service.list_workspaces.assert_awaited_once_with(
        name="acme", sort="name_asc", skip=10, limit=5
    )


def test_list_workspaces_requires_superadmin(
    client: TestClient,
    admin_service: AsyncMock,
    users_repo: AsyncMock,
    auth_headers: dict[str, str],
    principal_ids: tuple[UUID, UUID, UUID],
) -> None:
    _, _, user_id = principal_ids
    users_repo.get_by_id.return_value = _user(user_id, is_superadmin=False)
    response = client.get("/api/v1/admin/workspaces", headers=auth_headers)
    assert response.status_code == 403
    admin_service.list_workspaces.assert_not_called()


# ---------- suspend / restore ----------


def test_suspend_workspace_sets_timestamp_and_returns_row(
    client: TestClient, admin_service: AsyncMock, auth_headers: dict[str, str]
) -> None:
    ws_id = uuid4()
    now = datetime.now(UTC)
    admin_service.set_suspended.return_value = AdminWorkspaceRow(
        id=ws_id,
        name="Acme",
        slug="acme",
        task_prefix="ACME",
        suspended_at=now,
        created_at=now,
        updated_at=now,
        metrics=WorkspaceMetrics(total_users=0, total_tasks=0, total_tokens_used=0),
    )
    response = client.patch(
        f"/api/v1/admin/workspaces/{ws_id}/suspend",
        json={"is_suspended": True},
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["suspended_at"] is not None


def test_restore_workspace_clears_timestamp(
    client: TestClient, admin_service: AsyncMock, auth_headers: dict[str, str]
) -> None:
    ws_id = uuid4()
    now = datetime.now(UTC)
    admin_service.set_suspended.return_value = AdminWorkspaceRow(
        id=ws_id,
        name="Acme",
        slug="acme",
        task_prefix="ACME",
        suspended_at=None,
        created_at=now,
        updated_at=now,
        metrics=WorkspaceMetrics(total_users=1, total_tasks=2, total_tokens_used=3),
    )
    response = client.patch(
        f"/api/v1/admin/workspaces/{ws_id}/suspend",
        json={"is_suspended": False},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["suspended_at"] is None


def test_suspend_unknown_workspace_404s(
    client: TestClient, admin_service: AsyncMock, auth_headers: dict[str, str]
) -> None:
    admin_service.set_suspended.side_effect = WorkspaceNotFoundError("workspace not found")
    response = client.patch(
        f"/api/v1/admin/workspaces/{uuid4()}/suspend",
        json={"is_suspended": True},
        headers=auth_headers,
    )
    assert response.status_code == 404


def test_suspend_requires_superadmin(
    client: TestClient,
    admin_service: AsyncMock,
    users_repo: AsyncMock,
    auth_headers: dict[str, str],
    principal_ids: tuple[UUID, UUID, UUID],
) -> None:
    _, _, user_id = principal_ids
    users_repo.get_by_id.return_value = _user(user_id, is_superadmin=False)
    response = client.patch(
        f"/api/v1/admin/workspaces/{uuid4()}/suspend",
        json={"is_suspended": True},
        headers=auth_headers,
    )
    assert response.status_code == 403
    admin_service.set_suspended.assert_not_called()


# ---------- service-level tests ----------


@pytest.fixture
def repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(repo: AsyncMock) -> AdminWorkspaceService:
    return AdminWorkspaceService(workspaces=repo)


async def test_service_list_falls_back_on_unknown_sort(
    service: AdminWorkspaceService, repo: AsyncMock
) -> None:
    repo.list_with_metrics.return_value = ([], 0)
    await service.list_workspaces(sort="oh-no", limit=5)
    args = repo.list_with_metrics.await_args.kwargs
    assert args["sort"] == "created_at_desc"


async def test_service_suspend_idempotent_on_already_suspended(
    service: AdminWorkspaceService, repo: AsyncMock
) -> None:
    """Re-suspending an already-suspended workspace keeps the original
    timestamp — the DB write is skipped, so the audit trail stays
    honest. Metrics are still refreshed for the response."""
    ws_id = uuid4()
    original_stamp = datetime.now(UTC) - timedelta(days=2)
    repo.get_by_id.return_value = _workspace(workspace_id=ws_id, suspended_at=original_stamp)
    repo.get_metrics.return_value = (1, 2, 3)

    from app.application.admin.schemas import SuspendWorkspaceRequest

    row = await service.set_suspended(ws_id, SuspendWorkspaceRequest(is_suspended=True))
    assert row.suspended_at == original_stamp
    repo.set_suspended_at.assert_not_called()


async def test_service_restore_clears_when_active(
    service: AdminWorkspaceService, repo: AsyncMock
) -> None:
    """Restoring an already-active workspace is a no-op. Mirrors the
    suspend side for symmetry."""
    ws_id = uuid4()
    repo.get_by_id.return_value = _workspace(workspace_id=ws_id, suspended_at=None)
    repo.get_metrics.return_value = (0, 0, 0)

    from app.application.admin.schemas import SuspendWorkspaceRequest

    row = await service.set_suspended(ws_id, SuspendWorkspaceRequest(is_suspended=False))
    assert row.suspended_at is None
    repo.set_suspended_at.assert_not_called()


# Keeps the WorkspaceRowWithMetrics import referenced so ruff doesn't
# strip it — exercised indirectly via the repo fixtures, which mock
# the port's return shape.
_ = WorkspaceRowWithMetrics
