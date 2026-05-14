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
from app.domain.entities import Department, Member
from app.domain.enums import MemberRole, MemberType
from app.domain.exceptions import (
    DepartmentHeadNotInWorkspaceError,
    DepartmentNameConflictError,
    DepartmentNotFoundError,
    ForbiddenError,
    MemberAlreadyDepartmentHeadError,
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


def _dept(workspace_id, *, head_id=None) -> Department:
    now = datetime.now(UTC)
    return Department(
        id=uuid4(),
        workspace_id=workspace_id,
        name="Engineering",
        description="Builds the product.",
        head_id=head_id,
        created_at=now,
        updated_at=now,
    )


def _member(workspace_id, *, name: str = "Jane") -> Member:
    now = datetime.now(UTC)
    return Member(
        id=uuid4(),
        workspace_id=workspace_id,
        type=MemberType.HUMAN,
        name=name,
        email=f"{name.lower()}@example.com",
        priority=2,
        role=MemberRole.WORKSPACE_ADMIN,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def repo() -> AsyncMock:
    r = AsyncMock()
    # Default: no other department is headed by this member. Tests
    # that exercise the conflict explicitly override this.
    r.get_for_head.return_value = None
    return r


@pytest.fixture
def members() -> AsyncMock:
    """Mock MemberRepository — needed for head_id validation."""
    return AsyncMock()


@pytest.fixture
def service(repo: AsyncMock, members: AsyncMock) -> DepartmentService:
    return DepartmentService(departments=repo, members=members)


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


# ---------- create with head_id ----------


async def test_create_with_head_persists_head_id(
    service: DepartmentService, repo: AsyncMock, members: AsyncMock
) -> None:
    """When head_id is supplied and resolves to a workspace member,
    it lands on the persisted Department entity and the response
    embeds a Head summary."""
    p = _principal(role=MemberRole.WORKSPACE_ADMIN)
    head = _member(p.workspace_id, name="Alice")
    members.get_by_id.return_value = head
    repo.create.side_effect = lambda dept: dept  # passthrough

    response = await service.create(CreateDepartmentRequest(name="Eng", head_id=head.id), p)

    members.get_by_id.assert_awaited_once_with(head.id)
    created = repo.create.await_args.args[0]
    assert created.head_id == head.id
    assert response.head_id == head.id
    assert response.head is not None
    assert response.head.id == head.id
    assert response.head.name == "Alice"


async def test_create_with_head_in_other_workspace_raises(
    service: DepartmentService, repo: AsyncMock, members: AsyncMock
) -> None:
    p = _principal(role=MemberRole.WORKSPACE_ADMIN)
    foreign_head = _member(uuid4(), name="Eve")  # different workspace
    members.get_by_id.return_value = foreign_head
    with pytest.raises(DepartmentHeadNotInWorkspaceError):
        await service.create(CreateDepartmentRequest(name="Eng", head_id=foreign_head.id), p)
    repo.create.assert_not_called()


async def test_create_with_unknown_head_raises(
    service: DepartmentService, repo: AsyncMock, members: AsyncMock
) -> None:
    p = _principal(role=MemberRole.WORKSPACE_ADMIN)
    members.get_by_id.return_value = None
    with pytest.raises(DepartmentHeadNotInWorkspaceError):
        await service.create(CreateDepartmentRequest(name="Eng", head_id=uuid4()), p)
    repo.create.assert_not_called()


async def test_create_without_head_does_not_lookup(
    service: DepartmentService, repo: AsyncMock, members: AsyncMock
) -> None:
    """When head_id is omitted, the service must not call the member
    lookup. Saves a query on the common create-without-head path."""
    p = _principal(role=MemberRole.WORKSPACE_ADMIN)
    repo.create.side_effect = lambda dept: dept
    await service.create(CreateDepartmentRequest(name="Eng"), p)
    members.get_by_id.assert_not_called()


async def test_create_conflicts_when_head_already_heads_other_dept(
    service: DepartmentService, repo: AsyncMock, members: AsyncMock
) -> None:
    """A member can only head ONE department. If they already head
    another, the create call must surface
    ``MemberAlreadyDepartmentHeadError`` (mapped to 409 at the
    route) — the repo is NEVER asked to create the row."""
    p = _principal(role=MemberRole.WORKSPACE_ADMIN)
    head = _member(p.workspace_id, name="Alice")
    members.get_by_id.return_value = head
    existing = _dept(p.workspace_id, head_id=head.id)
    repo.get_for_head.return_value = existing

    with pytest.raises(MemberAlreadyDepartmentHeadError):
        await service.create(CreateDepartmentRequest(name="Eng", head_id=head.id), p)

    repo.get_for_head.assert_awaited_once_with(head.id)
    repo.create.assert_not_called()


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
        target.id,
        name=None,
        description=None,
        clear_description=True,
        head_id=None,
        clear_head=False,
    )


async def test_update_omits_description_field(service: DepartmentService, repo: AsyncMock) -> None:
    """Omitting description should not clear it. clear_description=False."""
    p = _principal()
    target = _dept(p.workspace_id)
    repo.get_by_id.return_value = target
    repo.update.return_value = target

    await service.update(target.id, UpdateDepartmentRequest(name="Eng2"), p)
    repo.update.assert_awaited_once_with(
        target.id,
        name="Eng2",
        description=None,
        clear_description=False,
        head_id=None,
        clear_head=False,
    )


# ---------- update head_id ----------


async def test_update_sets_head(
    service: DepartmentService, repo: AsyncMock, members: AsyncMock
) -> None:
    p = _principal()
    target = _dept(p.workspace_id)
    head = _member(p.workspace_id, name="Bob")
    repo.get_by_id.return_value = target
    members.get_by_id.return_value = head
    repo.update.return_value = _dept(p.workspace_id, head_id=head.id)

    response = await service.update(target.id, UpdateDepartmentRequest(head_id=head.id), p)
    repo.update.assert_awaited_once_with(
        target.id,
        name=None,
        description=None,
        clear_description=False,
        head_id=head.id,
        clear_head=False,
    )
    assert response.head_id == head.id
    assert response.head is not None and response.head.id == head.id


async def test_update_clears_head_explicitly(
    service: DepartmentService, repo: AsyncMock, members: AsyncMock
) -> None:
    """head_id=null in the body clears the FK rather than leaving it
    untouched. Mirrors the description-clear contract."""
    p = _principal()
    target = _dept(p.workspace_id, head_id=uuid4())
    repo.get_by_id.return_value = target
    repo.update.return_value = _dept(p.workspace_id, head_id=None)

    await service.update(
        target.id,
        UpdateDepartmentRequest.model_validate({"head_id": None}),
        p,
    )
    repo.update.assert_awaited_once_with(
        target.id,
        name=None,
        description=None,
        clear_description=False,
        head_id=None,
        clear_head=True,
    )
    members.get_by_id.assert_not_called()


async def test_update_head_other_workspace_raises(
    service: DepartmentService, repo: AsyncMock, members: AsyncMock
) -> None:
    p = _principal()
    target = _dept(p.workspace_id)
    repo.get_by_id.return_value = target
    members.get_by_id.return_value = _member(uuid4(), name="Eve")
    with pytest.raises(DepartmentHeadNotInWorkspaceError):
        await service.update(target.id, UpdateDepartmentRequest(head_id=uuid4()), p)
    repo.update.assert_not_called()


async def test_update_conflicts_when_head_already_heads_other_dept(
    service: DepartmentService, repo: AsyncMock, members: AsyncMock
) -> None:
    """Updating dept B to set head_id=X must conflict if X is already
    heading some other department A."""
    p = _principal()
    target = _dept(p.workspace_id)
    head = _member(p.workspace_id, name="Alice")
    other_dept = _dept(p.workspace_id, head_id=head.id)
    repo.get_by_id.return_value = target
    members.get_by_id.return_value = head
    repo.get_for_head.return_value = other_dept

    with pytest.raises(MemberAlreadyDepartmentHeadError):
        await service.update(target.id, UpdateDepartmentRequest(head_id=head.id), p)
    repo.update.assert_not_called()


async def test_update_keeping_same_head_does_not_conflict(
    service: DepartmentService, repo: AsyncMock, members: AsyncMock
) -> None:
    """The conflict check must exclude the department being edited
    itself — re-saving a department with its already-current head is
    a no-op, not a conflict."""
    p = _principal()
    head = _member(p.workspace_id, name="Alice")
    target = _dept(p.workspace_id, head_id=head.id)
    repo.get_by_id.return_value = target
    members.get_by_id.return_value = head
    # The repo would normally return ``target`` for this lookup —
    # which is the SAME department being edited. Service must treat
    # that as "no other department headed by this member".
    repo.get_for_head.return_value = target
    repo.update.return_value = target

    response = await service.update(target.id, UpdateDepartmentRequest(head_id=head.id), p)
    assert response.head_id == head.id
    repo.update.assert_awaited_once()


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
