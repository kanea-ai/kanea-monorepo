"""Smoke tests for audit-trail write hooks on the application services.

These verify the *fact* that an audit row is recorded — the visibility
tests live in test_audit_visibility.py. We mock the AuditLogService to
assert each mutation produces the right (action, resource_type, changes)
shape without going through the SQL layer.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.application.departments.schemas import (
    CreateDepartmentRequest,
    UpdateDepartmentRequest,
)
from app.application.departments.service import DepartmentService
from app.application.tasks.schemas import Principal
from app.application.tenants.schemas import (
    SetMemberSuspensionRequest,
    UpdateMemberProfileRequest,
)
from app.application.tenants.service import InviteService
from app.domain.entities import Department, Member
from app.domain.enums import (
    AuditAction,
    AuditResourceType,
    MemberRole,
    MemberType,
)


def _principal() -> Principal:
    return Principal(
        member_id=uuid4(),
        workspace_id=uuid4(),
        type=MemberType.HUMAN,
        priority=1,
        scope="human",
        role=MemberRole.WORKSPACE_OWNER,
    )


def _dept(workspace_id) -> Department:
    now = datetime.now(UTC)
    return Department(
        id=uuid4(),
        workspace_id=workspace_id,
        name="Engineering",
        description=None,
        created_at=now,
        updated_at=now,
    )


def _member(workspace_id, *, role=MemberRole.WORKSPACE_USER, suspended=False) -> Member:
    now = datetime.now(UTC)
    return Member(
        id=uuid4(),
        workspace_id=workspace_id,
        type=MemberType.HUMAN,
        name="Bob",
        email="b@example.com",
        priority=5,
        role=role,
        is_suspended=suspended,
        created_at=now,
        updated_at=now,
    )


# ---------- Department audit writes ----------


@pytest.fixture
def dept_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def audit_logs() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def dept_service(dept_repo: AsyncMock, audit_logs: AsyncMock) -> DepartmentService:
    return DepartmentService(departments=dept_repo, audit_logs=audit_logs)


async def test_create_department_records_audit(
    dept_service: DepartmentService, dept_repo: AsyncMock, audit_logs: AsyncMock
) -> None:
    p = _principal()
    created = _dept(p.workspace_id)
    dept_repo.create.return_value = created

    await dept_service.create(CreateDepartmentRequest(name="Engineering"), p)

    audit_logs.record.assert_awaited_once()
    kwargs = audit_logs.record.await_args.kwargs
    assert kwargs["action"] is AuditAction.CREATED
    assert kwargs["resource_type"] is AuditResourceType.DEPARTMENT
    assert kwargs["resource_id"] == created.id
    assert kwargs["changes"]["name"] == "Engineering"


async def test_update_department_records_diff(
    dept_service: DepartmentService, dept_repo: AsyncMock, audit_logs: AsyncMock
) -> None:
    p = _principal()
    before = _dept(p.workspace_id)
    after = Department(
        id=before.id,
        workspace_id=before.workspace_id,
        name="Eng",
        description="now with description",
        created_at=before.created_at,
        updated_at=datetime.now(UTC),
    )
    dept_repo.get_by_id.return_value = before
    dept_repo.update.return_value = after

    await dept_service.update(
        before.id, UpdateDepartmentRequest(name="Eng", description="now with description"), p
    )

    kwargs = audit_logs.record.await_args.kwargs
    assert kwargs["action"] is AuditAction.UPDATED
    assert "name" in kwargs["changes"]
    assert kwargs["changes"]["name"] == {"from": "Engineering", "to": "Eng"}
    assert kwargs["changes"]["description"] == {
        "from": None,
        "to": "now with description",
    }


async def test_update_department_with_no_changes_skips_audit(
    dept_service: DepartmentService, dept_repo: AsyncMock, audit_logs: AsyncMock
) -> None:
    """A PATCH that doesn't change anything (e.g. name omitted, no
    description in body) shouldn't produce a noisy "no-op" audit row."""
    p = _principal()
    before = _dept(p.workspace_id)
    dept_repo.get_by_id.return_value = before
    dept_repo.update.return_value = before

    await dept_service.update(before.id, UpdateDepartmentRequest(), p)
    audit_logs.record.assert_not_called()


async def test_delete_department_records_audit(
    dept_service: DepartmentService, dept_repo: AsyncMock, audit_logs: AsyncMock
) -> None:
    p = _principal()
    target = _dept(p.workspace_id)
    dept_repo.get_by_id.return_value = target

    await dept_service.delete(target.id, p)
    kwargs = audit_logs.record.await_args.kwargs
    assert kwargs["action"] is AuditAction.DELETED
    assert kwargs["resource_id"] == target.id


# ---------- Member audit writes via InviteService ----------


@pytest.fixture
def members_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def invite_service(members_repo: AsyncMock, audit_logs: AsyncMock) -> InviteService:
    return InviteService(
        invites=AsyncMock(),
        members=members_repo,
        workspaces=AsyncMock(),
        auth_members=AsyncMock(),
        credentials=AsyncMock(),
        hasher=AsyncMock(),
        tokens=AsyncMock(),
        accept_url_base="http://example",
        audit_logs=audit_logs,
    )


async def test_suspending_a_member_records_audit(
    invite_service: InviteService, members_repo: AsyncMock, audit_logs: AsyncMock
) -> None:
    p = _principal()
    target = _member(p.workspace_id)
    members_repo.get_by_id.return_value = target
    members_repo.set_suspended.return_value = target

    await invite_service.set_member_suspension(
        target.id, SetMemberSuspensionRequest(is_suspended=True), p
    )

    kwargs = audit_logs.record.await_args.kwargs
    assert kwargs["action"] is AuditAction.SUSPENDED
    assert kwargs["resource_type"] is AuditResourceType.MEMBER
    assert kwargs["changes"]["member_name"] == target.name


async def test_revoking_suspension_records_revoked_action(
    invite_service: InviteService, members_repo: AsyncMock, audit_logs: AsyncMock
) -> None:
    p = _principal()
    target = _member(p.workspace_id, suspended=True)
    members_repo.get_by_id.return_value = target
    members_repo.set_suspended.return_value = target

    await invite_service.set_member_suspension(
        target.id, SetMemberSuspensionRequest(is_suspended=False), p
    )

    kwargs = audit_logs.record.await_args.kwargs
    assert kwargs["action"] is AuditAction.SUSPENSION_REVOKED


async def test_no_op_suspend_skips_audit(
    invite_service: InviteService, members_repo: AsyncMock, audit_logs: AsyncMock
) -> None:
    """Re-suspending an already-suspended member shouldn't write a
    duplicate audit row."""
    p = _principal()
    target = _member(p.workspace_id, suspended=True)
    members_repo.get_by_id.return_value = target
    members_repo.set_suspended.return_value = target

    await invite_service.set_member_suspension(
        target.id, SetMemberSuspensionRequest(is_suspended=True), p
    )
    audit_logs.record.assert_not_called()


async def test_role_change_records_role_changed_action(
    invite_service: InviteService, members_repo: AsyncMock, audit_logs: AsyncMock
) -> None:
    p = _principal()
    target = _member(p.workspace_id, role=MemberRole.WORKSPACE_USER)
    promoted = _member(p.workspace_id, role=MemberRole.WORKSPACE_ADMIN)
    promoted.id = target.id
    members_repo.get_by_id.return_value = target
    members_repo.update_profile.return_value = promoted

    await invite_service.update_member_profile(
        target.id, UpdateMemberProfileRequest(role=MemberRole.WORKSPACE_ADMIN), p
    )

    kwargs = audit_logs.record.await_args.kwargs
    assert kwargs["action"] is AuditAction.ROLE_CHANGED
    assert kwargs["changes"]["from"] == MemberRole.WORKSPACE_USER.value
    assert kwargs["changes"]["to"] == MemberRole.WORKSPACE_ADMIN.value
