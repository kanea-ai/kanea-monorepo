"""Tests for AuditLogService visibility scoping.

The matrix:
- Owner: every row in the workspace.
- Admin priority ≤ 2: DEPARTMENT/TEAM/MEMBER rows.
- Admin priority ≤ 3: TEAM rows for teams the principal MANAGES,
  plus every team in any department they HEAD (head_id link on
  ``departments``).
- Anyone else: empty list.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.application.audit.service import AuditLogService
from app.application.tasks.schemas import Principal
from app.domain.entities import Member
from app.domain.enums import (
    AuditResourceType,
    MemberRole,
    MemberType,
    TeamRole,
)


def _principal(
    *,
    role: MemberRole,
    priority: int,
    member_id=None,
    workspace_id=None,
) -> Principal:
    return Principal(
        member_id=member_id or uuid4(),
        workspace_id=workspace_id or uuid4(),
        type=MemberType.HUMAN,
        priority=priority,
        scope="human",
        role=role,
    )


def _member(workspace_id, member_id, *, team_id=None, team_role=None) -> Member:
    now = datetime.now(UTC)
    return Member(
        id=member_id,
        workspace_id=workspace_id,
        type=MemberType.HUMAN,
        name="Alice",
        email="a@example.com",
        priority=3,
        role=MemberRole.WORKSPACE_ADMIN,
        team_id=team_id,
        team_role=team_role,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def audit_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def members_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def teams_repo() -> AsyncMock:
    repo = AsyncMock()
    # Default: principal is not the head of any department.
    repo.list_team_ids_for_department_head.return_value = []
    return repo


@pytest.fixture
def service(
    audit_repo: AsyncMock, members_repo: AsyncMock, teams_repo: AsyncMock
) -> AuditLogService:
    return AuditLogService(audit_logs=audit_repo, members=members_repo, teams=teams_repo)


# ---------- visibility rules ----------


async def test_owner_sees_everything(service: AuditLogService, audit_repo: AsyncMock) -> None:
    """Owner: no resource_types narrowing, no team narrowing."""
    p = _principal(role=MemberRole.WORKSPACE_OWNER, priority=1)
    audit_repo.list_for_workspace.return_value = ([], 0)
    await service.list_for_principal(p)
    audit_repo.list_for_workspace.assert_awaited_once()
    kwargs = audit_repo.list_for_workspace.await_args.kwargs
    assert kwargs["resource_types"] is None
    assert kwargs["team_resource_ids"] is None


async def test_priority_2_admin_sees_department_team_member(
    service: AuditLogService, audit_repo: AsyncMock
) -> None:
    p = _principal(role=MemberRole.WORKSPACE_ADMIN, priority=2)
    audit_repo.list_for_workspace.return_value = ([], 0)
    await service.list_for_principal(p)
    kwargs = audit_repo.list_for_workspace.await_args.kwargs
    assert set(kwargs["resource_types"]) == {
        AuditResourceType.DEPARTMENT,
        AuditResourceType.TEAM,
        AuditResourceType.MEMBER,
    }
    assert kwargs["team_resource_ids"] is None


async def test_priority_3_admin_manager_sees_own_team(
    service: AuditLogService, audit_repo: AsyncMock, members_repo: AsyncMock
) -> None:
    """A P3 admin who is MANAGER of one team should see TEAM rows
    narrowed to that team. (HEAD was removed from TeamRole in
    migration 0022; team-level oversight is now MANAGER alone.)"""
    workspace_id = uuid4()
    member_id = uuid4()
    team_id = uuid4()
    p = _principal(
        role=MemberRole.WORKSPACE_ADMIN,
        priority=3,
        member_id=member_id,
        workspace_id=workspace_id,
    )
    members_repo.get_by_id.return_value = _member(
        workspace_id, member_id, team_id=team_id, team_role=TeamRole.MANAGER
    )
    audit_repo.list_for_workspace.return_value = ([], 0)

    await service.list_for_principal(p)
    kwargs = audit_repo.list_for_workspace.await_args.kwargs
    assert kwargs["resource_types"] == [AuditResourceType.TEAM]
    assert kwargs["team_resource_ids"] == [team_id]


async def test_priority_3_admin_department_head_sees_all_dept_teams(
    service: AuditLogService,
    audit_repo: AsyncMock,
    members_repo: AsyncMock,
    teams_repo: AsyncMock,
) -> None:
    """A P3 admin who is the head of a department (departments.head_id
    == member.id) should see TEAM rows for every team in that
    department, even if they hold no team_role themselves."""
    workspace_id = uuid4()
    member_id = uuid4()
    dept_team_a = uuid4()
    dept_team_b = uuid4()
    p = _principal(
        role=MemberRole.WORKSPACE_ADMIN,
        priority=3,
        member_id=member_id,
        workspace_id=workspace_id,
    )
    # No team_role on the principal — reach comes from being head of a
    # department.
    members_repo.get_by_id.return_value = _member(
        workspace_id, member_id, team_id=None, team_role=None
    )
    teams_repo.list_team_ids_for_department_head.return_value = [dept_team_a, dept_team_b]
    audit_repo.list_for_workspace.return_value = ([], 0)

    await service.list_for_principal(p)
    kwargs = audit_repo.list_for_workspace.await_args.kwargs
    assert kwargs["resource_types"] == [AuditResourceType.TEAM]
    assert set(kwargs["team_resource_ids"]) == {dept_team_a, dept_team_b}


async def test_priority_3_admin_manager_and_department_head_union(
    service: AuditLogService,
    audit_repo: AsyncMock,
    members_repo: AsyncMock,
    teams_repo: AsyncMock,
) -> None:
    """When the principal is BOTH a MANAGER on their own team AND
    head of a department, audit reach is the union of both team
    sets."""
    workspace_id = uuid4()
    member_id = uuid4()
    own_team = uuid4()
    dept_team = uuid4()
    p = _principal(
        role=MemberRole.WORKSPACE_ADMIN,
        priority=3,
        member_id=member_id,
        workspace_id=workspace_id,
    )
    members_repo.get_by_id.return_value = _member(
        workspace_id, member_id, team_id=own_team, team_role=TeamRole.MANAGER
    )
    teams_repo.list_team_ids_for_department_head.return_value = [dept_team]
    audit_repo.list_for_workspace.return_value = ([], 0)

    await service.list_for_principal(p)
    kwargs = audit_repo.list_for_workspace.await_args.kwargs
    assert set(kwargs["team_resource_ids"]) == {own_team, dept_team}


async def test_priority_3_admin_with_member_team_role_sees_nothing(
    service: AuditLogService, audit_repo: AsyncMock, members_repo: AsyncMock
) -> None:
    """A P3 admin whose only team role is MEMBER doesn't oversee
    anything — they should get an empty list."""
    workspace_id = uuid4()
    member_id = uuid4()
    p = _principal(
        role=MemberRole.WORKSPACE_ADMIN,
        priority=3,
        member_id=member_id,
        workspace_id=workspace_id,
    )
    members_repo.get_by_id.return_value = _member(
        workspace_id, member_id, team_id=uuid4(), team_role=TeamRole.MEMBER
    )

    audit_repo.list_for_workspace.return_value = ([], 0)
    page = await service.list_for_principal(p)
    assert page.items == []
    assert page.total == 0
    # Ensure we still hit the repo with an empty team_resource_ids
    # narrowing (which the repo's short-circuit handles cheaply).
    kwargs = audit_repo.list_for_workspace.await_args.kwargs
    assert kwargs["team_resource_ids"] == []


async def test_priority_4_admin_sees_nothing(
    service: AuditLogService, audit_repo: AsyncMock
) -> None:
    """No matrix slot for P4+ admins — they fall through to the "no
    rows" sentinel and the repo is not called."""
    p = _principal(role=MemberRole.WORKSPACE_ADMIN, priority=4)
    page = await service.list_for_principal(p)
    assert page.items == []
    assert page.total == 0
    audit_repo.list_for_workspace.assert_not_called()


async def test_user_role_sees_nothing(service: AuditLogService, audit_repo: AsyncMock) -> None:
    """USER role sees nothing — the route layer also rejects this
    with 403, but the service is the belt to the route's braces."""
    p = _principal(role=MemberRole.WORKSPACE_USER, priority=1)
    page = await service.list_for_principal(p)
    assert page.items == []
    assert page.total == 0
    audit_repo.list_for_workspace.assert_not_called()
