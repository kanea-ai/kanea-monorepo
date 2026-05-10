"""Unit tests for DepartmentService.

Contract:
- Anyone in the workspace can list / get departments (it's an
  organisational tag, not a permission boundary).
- Only WORKSPACE_OWNER / WORKSPACE_ADMIN can create / update / delete.
- Cross-tenant department ids 404 (same shape as truly-missing so
  existence isn't leaked).
- Per-workspace name uniqueness raises DepartmentNameConflictError
  (mapped to 409 at the route).
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.application.departments.schemas import (
    CreateDepartmentRequest,
    UpdateDepartmentRequest,
)
from app.application.departments.service import DepartmentService
from app.application.tasks.schemas import Principal
from app.domain.entities import Department
from app.domain.enums import MemberRole, MemberType
from app.domain.exceptions import (
    DepartmentNameConflictError,
    DepartmentNotFoundError,
    ForbiddenError,
)


def _principal(*, role: MemberRole = MemberRole.WORKSPACE_OWNER, workspace_id=None) -> Principal:
    return Principal(
        member_id=uuid4(),
        workspace_id=workspace_id or uuid4(),
        type=MemberType.HUMAN,
        priority=1,
        scope="human",
        role=role,
    )


def _dept(workspace_id) -> Department:
    now = datetime.now(UTC)
    return Department(
        id=uuid4(),
        workspace_id=workspace_id,
        name="Engineering",
        description="Builds the product.",
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(repo: AsyncMock) -> DepartmentService:
    return DepartmentService(departments=repo)


# ---------- list / get ----------


async def test_member_can_list(service: DepartmentService, repo: AsyncMock) -> None:
    p = _principal(role=MemberRole.WORKSPACE_USER)
    repo.list_for_workspace.return_value = ([_dept(p.workspace_id)], 1)
    page = await service.list_for_workspace(p)
    assert page.total == 1
    assert len(page.items) == 1
    repo.list_for_workspace.assert_awaited_once_with(p.workspace_id, name=None, skip=0, limit=None)


async def test_list_passes_name_filter(service: DepartmentService, repo: AsyncMock) -> None:
    p = _principal()
    repo.list_for_workspace.return_value = ([], 0)
    await service.list_for_workspace(p, name="eng")
    repo.list_for_workspace.assert_awaited_once_with(p.workspace_id, name="eng", skip=0, limit=None)


async def test_list_paginates(service: DepartmentService, repo: AsyncMock) -> None:
    """skip / limit forward to the repo and the service surfaces the
    repo's total count untouched."""
    p = _principal()
    repo.list_for_workspace.return_value = ([], 17)
    page = await service.list_for_workspace(p, skip=5, limit=3)
    assert page.total == 17
    repo.list_for_workspace.assert_awaited_once_with(p.workspace_id, name=None, skip=5, limit=3)


async def test_get_cross_tenant_404s(service: DepartmentService, repo: AsyncMock) -> None:
    p = _principal()
    repo.get_by_id.return_value = _dept(uuid4())  # other workspace
    with pytest.raises(DepartmentNotFoundError):
        await service.get_by_id(uuid4(), p)


# ---------- create ----------


async def test_member_role_cannot_create(service: DepartmentService) -> None:
    p = _principal(role=MemberRole.WORKSPACE_USER)
    with pytest.raises(ForbiddenError):
        await service.create(CreateDepartmentRequest(name="Eng"), p)


async def test_admin_can_create(service: DepartmentService, repo: AsyncMock) -> None:
    p = _principal(role=MemberRole.WORKSPACE_ADMIN)
    created = _dept(p.workspace_id)
    repo.create.return_value = created
    result = await service.create(CreateDepartmentRequest(name="Eng", description="x"), p)
    assert result.id == created.id
    repo.create.assert_awaited_once()


async def test_create_name_conflict_raises(service: DepartmentService, repo: AsyncMock) -> None:
    p = _principal()
    repo.create.side_effect = IntegrityError("unique", params=None, orig=Exception())
    with pytest.raises(DepartmentNameConflictError):
        await service.create(CreateDepartmentRequest(name="Eng"), p)


# ---------- update ----------


async def test_member_role_cannot_update(service: DepartmentService) -> None:
    p = _principal(role=MemberRole.WORKSPACE_USER)
    with pytest.raises(ForbiddenError):
        await service.update(uuid4(), UpdateDepartmentRequest(name="Eng2"), p)


async def test_update_cross_tenant_404s(service: DepartmentService, repo: AsyncMock) -> None:
    p = _principal()
    repo.get_by_id.return_value = _dept(uuid4())  # other workspace
    with pytest.raises(DepartmentNotFoundError):
        await service.update(uuid4(), UpdateDepartmentRequest(name="X"), p)


async def test_update_clears_description_explicitly(
    service: DepartmentService, repo: AsyncMock
) -> None:
    """Setting description=null in the body should clear the field
    rather than leave it untouched. This mirrors the projects API
    contract."""
    p = _principal()
    target = _dept(p.workspace_id)
    repo.get_by_id.return_value = target
    repo.update.return_value = target

    await service.update(
        target.id,
        UpdateDepartmentRequest.model_validate({"description": None}),
        p,
    )
    repo.update.assert_awaited_once_with(
        target.id, name=None, description=None, clear_description=True
    )


async def test_update_omits_description_field(service: DepartmentService, repo: AsyncMock) -> None:
    """Omitting description should not clear it. clear_description=False."""
    p = _principal()
    target = _dept(p.workspace_id)
    repo.get_by_id.return_value = target
    repo.update.return_value = target

    await service.update(target.id, UpdateDepartmentRequest(name="Eng2"), p)
    repo.update.assert_awaited_once_with(
        target.id, name="Eng2", description=None, clear_description=False
    )


# ---------- delete ----------


async def test_member_role_cannot_delete(service: DepartmentService) -> None:
    p = _principal(role=MemberRole.WORKSPACE_USER)
    with pytest.raises(ForbiddenError):
        await service.delete(uuid4(), p)


async def test_admin_can_delete(service: DepartmentService, repo: AsyncMock) -> None:
    p = _principal(role=MemberRole.WORKSPACE_ADMIN)
    target = _dept(p.workspace_id)
    repo.get_by_id.return_value = target
    await service.delete(target.id, p)
    repo.delete.assert_awaited_once_with(target.id)


async def test_delete_cross_tenant_404s(service: DepartmentService, repo: AsyncMock) -> None:
    p = _principal()
    repo.get_by_id.return_value = _dept(uuid4())
    with pytest.raises(DepartmentNotFoundError):
        await service.delete(uuid4(), p)
    repo.delete.assert_not_called()
