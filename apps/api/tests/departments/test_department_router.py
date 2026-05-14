"""Route-level tests for /api/v1/departments.

Verifies that the WorkspaceAdminDep guard is wired on POST/PATCH/DELETE
and that the GET surface is reachable for plain MEMBER tokens. The
service layer is mocked — these tests are about HTTP semantics and
RBAC plumbing, not the business rules (those live in the service
unit tests)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import jwt
import pytest
from fastapi.testclient import TestClient

from app.api.deps import (
    DepartmentServiceDep,
    get_current_principal,
    get_department_service,
)
from app.application.departments.schemas import DepartmentResponse
from app.application.tasks.schemas import Principal
from app.core.config import settings
from app.domain.enums import MemberRole, MemberType
from app.main import app


def _bearer(role: str) -> dict[str, str]:
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


def _override_principal(role: MemberRole) -> Principal:
    return Principal(
        member_id=uuid4(),
        workspace_id=uuid4(),
        type=MemberType.HUMAN,
        priority=1,
        scope="human",
        role=role,
    )


@pytest.fixture
def dept_service_mock() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def client(dept_service_mock: AsyncMock) -> Iterator[TestClient]:
    """Test client wired with the dept service mock + a get_current_principal
    override so the suspension DB lookup is bypassed in route tests."""
    app.dependency_overrides[get_department_service] = lambda: dept_service_mock

    # The route's effective role is taken from the Authorization header
    # JWT (decoded by _decode_principal). We still override
    # get_current_principal so the DB-touching suspension check is
    # short-circuited; the role we hand back must match the JWT's role
    # claim per-test, hence ``_override_principal`` is set inside each
    # test rather than here.
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _stub_dept(workspace_id: UUID) -> DepartmentResponse:
    now = datetime.now(UTC)
    return DepartmentResponse(
        id=uuid4(),
        workspace_id=workspace_id,
        name="Engineering",
        description="x",
        head_id=None,
        head=None,
        created_at=now,
        updated_at=now,
    )


def test_list_works_for_plain_member(client: TestClient, dept_service_mock: AsyncMock) -> None:
    p = _override_principal(MemberRole.WORKSPACE_USER)
    app.dependency_overrides[get_current_principal] = lambda: p
    # Paginated response shape — ``items`` + ``total``.
    from app.application.departments.schemas import DepartmentResponse
    from app.application.pagination import Page

    dept_service_mock.list_for_workspace.return_value = Page[DepartmentResponse](
        items=[_stub_dept(p.workspace_id)], total=1
    )
    response = client.get("/api/v1/departments", headers=_bearer("WORKSPACE_USER"))
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1


def test_post_rejects_member_role(client: TestClient, dept_service_mock: AsyncMock) -> None:
    p = _override_principal(MemberRole.WORKSPACE_USER)
    app.dependency_overrides[get_current_principal] = lambda: p
    response = client.post(
        "/api/v1/departments",
        json={"name": "Eng"},
        headers=_bearer("WORKSPACE_USER"),
    )
    assert response.status_code == 403
    dept_service_mock.create.assert_not_called()


def test_post_accepts_admin(client: TestClient, dept_service_mock: AsyncMock) -> None:
    p = _override_principal(MemberRole.WORKSPACE_ADMIN)
    app.dependency_overrides[get_current_principal] = lambda: p
    dept_service_mock.create.return_value = _stub_dept(p.workspace_id)
    response = client.post(
        "/api/v1/departments",
        json={"name": "Eng", "description": "Builds the product."},
        headers=_bearer("WORKSPACE_ADMIN"),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Engineering"
    dept_service_mock.create.assert_awaited_once()


def test_patch_rejects_member_role(client: TestClient, dept_service_mock: AsyncMock) -> None:
    p = _override_principal(MemberRole.WORKSPACE_USER)
    app.dependency_overrides[get_current_principal] = lambda: p
    response = client.patch(
        f"/api/v1/departments/{uuid4()}",
        json={"name": "X"},
        headers=_bearer("WORKSPACE_USER"),
    )
    assert response.status_code == 403


def test_delete_rejects_member_role(client: TestClient, dept_service_mock: AsyncMock) -> None:
    p = _override_principal(MemberRole.WORKSPACE_USER)
    app.dependency_overrides[get_current_principal] = lambda: p
    response = client.delete(
        f"/api/v1/departments/{uuid4()}",
        headers=_bearer("WORKSPACE_USER"),
    )
    assert response.status_code == 403


# Suppress unused-fixture warning for the typed Annotated import.
_ = DepartmentServiceDep
