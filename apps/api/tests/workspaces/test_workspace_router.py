"""Route-level tests for PATCH /api/v1/workspaces/{id}.

Verifies the role/path guard plumbing. The business rules
(slug regeneration, conflict mapping) are covered in
``test_workspace_service``."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.deps import (
    get_current_principal,
    get_workspace_service,
)
from app.application.tasks.schemas import Principal
from app.application.workspaces.schemas import WorkspaceResponse
from app.domain.enums import MemberRole, MemberType
from app.main import app


def _principal(*, role: MemberRole, workspace_id: UUID) -> Principal:
    return Principal(
        member_id=uuid4(),
        workspace_id=workspace_id,
        type=MemberType.HUMAN,
        priority=1,
        scope="human",
        role=role,
    )


def _stub_ws(workspace_id: UUID, name: str = "New") -> WorkspaceResponse:
    now = datetime.now(UTC)
    return WorkspaceResponse(
        id=workspace_id,
        name=name,
        slug=f"{name.lower()}-abc123",
        task_prefix="NEW",
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def ws_service_mock() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def client(ws_service_mock: AsyncMock) -> Iterator[TestClient]:
    app.dependency_overrides[get_workspace_service] = lambda: ws_service_mock
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_owner_rename_200(client: TestClient, ws_service_mock: AsyncMock) -> None:
    ws_id = uuid4()
    p = _principal(role=MemberRole.WORKSPACE_OWNER, workspace_id=ws_id)
    app.dependency_overrides[get_current_principal] = lambda: p
    ws_service_mock.rename.return_value = _stub_ws(ws_id, name="Renamed")

    r = client.patch(
        f"/api/v1/workspaces/{ws_id}",
        json={"name": "Renamed"},
        headers={"Authorization": "Bearer dummy"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Renamed"


def test_admin_role_rejected_403(client: TestClient, ws_service_mock: AsyncMock) -> None:
    """Admins can manage members/teams/departments but NOT rename the
    workspace itself — that's owner-only."""
    from app.domain.exceptions import ForbiddenError

    ws_id = uuid4()
    p = _principal(role=MemberRole.WORKSPACE_ADMIN, workspace_id=ws_id)
    app.dependency_overrides[get_current_principal] = lambda: p
    ws_service_mock.rename.side_effect = ForbiddenError("workspace owner role required")

    r = client.patch(
        f"/api/v1/workspaces/{ws_id}",
        json={"name": "Renamed"},
        headers={"Authorization": "Bearer dummy"},
    )
    assert r.status_code == 403


def test_user_role_rejected_403(client: TestClient, ws_service_mock: AsyncMock) -> None:
    from app.domain.exceptions import ForbiddenError

    ws_id = uuid4()
    p = _principal(role=MemberRole.WORKSPACE_USER, workspace_id=ws_id)
    app.dependency_overrides[get_current_principal] = lambda: p
    ws_service_mock.rename.side_effect = ForbiddenError("workspace owner role required")

    r = client.patch(
        f"/api/v1/workspaces/{ws_id}",
        json={"name": "Renamed"},
        headers={"Authorization": "Bearer dummy"},
    )
    assert r.status_code == 403


def test_conflict_409(client: TestClient, ws_service_mock: AsyncMock) -> None:
    from app.domain.exceptions import WorkspaceNameConflictError

    ws_id = uuid4()
    p = _principal(role=MemberRole.WORKSPACE_OWNER, workspace_id=ws_id)
    app.dependency_overrides[get_current_principal] = lambda: p
    ws_service_mock.rename.side_effect = WorkspaceNameConflictError(
        "a workspace with that name already exists"
    )

    r = client.patch(
        f"/api/v1/workspaces/{ws_id}",
        json={"name": "Taken"},
        headers={"Authorization": "Bearer dummy"},
    )
    assert r.status_code == 409
    assert "already exists" in r.json()["detail"]


def test_cross_workspace_path_404(client: TestClient, ws_service_mock: AsyncMock) -> None:
    """Owner of workspace A trying to PATCH workspace B's id surfaces
    as 404, not 403 — tenant isolation."""
    from app.domain.exceptions import WorkspaceNotFoundError

    own_id = uuid4()
    other_id = uuid4()
    p = _principal(role=MemberRole.WORKSPACE_OWNER, workspace_id=own_id)
    app.dependency_overrides[get_current_principal] = lambda: p
    ws_service_mock.rename.side_effect = WorkspaceNotFoundError("workspace not found")

    r = client.patch(
        f"/api/v1/workspaces/{other_id}",
        json={"name": "Hijack"},
        headers={"Authorization": "Bearer dummy"},
    )
    assert r.status_code == 404


def test_empty_name_422(client: TestClient, ws_service_mock: AsyncMock) -> None:
    ws_id = uuid4()
    p = _principal(role=MemberRole.WORKSPACE_OWNER, workspace_id=ws_id)
    app.dependency_overrides[get_current_principal] = lambda: p
    r = client.patch(
        f"/api/v1/workspaces/{ws_id}",
        json={"name": ""},
        headers={"Authorization": "Bearer dummy"},
    )
    assert r.status_code == 422
