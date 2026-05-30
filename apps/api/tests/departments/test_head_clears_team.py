"""Hierarchy rule: a Department Head does NOT belong to a Team.

When ``head_id`` is set on a department (create or update), the
referenced member's ``team_id`` and ``team_role`` must be cleared to
NULL in the same write so the hierarchy stays consistent: a Head sits
above team-level leadership, not inside a single team.
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
from app.domain.entities import Department, Member
from app.domain.enums import MemberRole, MemberType, TeamRole


def _principal(*, role: MemberRole = MemberRole.WORKSPACE_OWNER, workspace_id=None) -> Principal:
    return Principal(
        member_id=uuid4(),
        workspace_id=workspace_id or uuid4(),
        type=MemberType.HUMAN,
        priority=1,
        scope="human",
        role=role,
    )


def _member(
    workspace_id,
    *,
    name: str = "Jane",
    team_id=None,
    team_role: TeamRole | None = None,
) -> Member:
    now = datetime.now(UTC)
    return Member(
        id=uuid4(),
        workspace_id=workspace_id,
        type=MemberType.HUMAN,
        name=name,
        email=f"{name.lower()}@example.com",
        priority=2,
        role=MemberRole.WORKSPACE_ADMIN,
        team_id=team_id,
        team_role=team_role,
        created_at=now,
        updated_at=now,
    )


def _dept(workspace_id, *, head_id=None) -> Department:
    now = datetime.now(UTC)
    return Department(
        id=uuid4(),
        workspace_id=workspace_id,
        name="Engineering",
        description="",
        head_id=head_id,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def repo() -> AsyncMock:
    r = AsyncMock()
    r.get_for_head.return_value = None
    return r


@pytest.fixture
def members() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(repo: AsyncMock, members: AsyncMock) -> DepartmentService:
    return DepartmentService(departments=repo, members=members)


async def test_create_with_head_clears_member_team(
    service: DepartmentService, repo: AsyncMock, members: AsyncMock
) -> None:
    p = _principal()
    head = _member(p.workspace_id, team_id=uuid4(), team_role=TeamRole.MANAGER)
    members.get_by_id.return_value = head
    repo.create.return_value = _dept(p.workspace_id, head_id=head.id)

    await service.create(
        CreateDepartmentRequest(name="Eng", head_id=head.id),
        p,
    )
    members.set_team.assert_awaited_once_with(head.id, team_id=None, team_role=None)


async def test_update_assigning_head_clears_member_team(
    service: DepartmentService, repo: AsyncMock, members: AsyncMock
) -> None:
    p = _principal()
    existing = _dept(p.workspace_id, head_id=None)
    head = _member(p.workspace_id, team_id=uuid4(), team_role=TeamRole.LEAD)
    repo.get_by_id.return_value = existing
    members.get_by_id.return_value = head
    repo.update.return_value = _dept(p.workspace_id, head_id=head.id)

    await service.update(
        existing.id,
        UpdateDepartmentRequest(head_id=head.id),
        p,
    )
    members.set_team.assert_awaited_once_with(head.id, team_id=None, team_role=None)


async def test_update_clearing_head_does_not_touch_member_team(
    service: DepartmentService, repo: AsyncMock, members: AsyncMock
) -> None:
    """Removing a head (head_id=null) just clears the FK on the department;
    we don't touch the (now-former) head's team assignment — that's an
    explicit admin decision via PATCH /tenants/members/{id}/team."""
    p = _principal()
    existing = _dept(p.workspace_id, head_id=uuid4())
    repo.get_by_id.return_value = existing
    repo.update.return_value = _dept(p.workspace_id, head_id=None)

    await service.update(
        existing.id,
        UpdateDepartmentRequest.model_validate({"head_id": None}),
        p,
    )
    members.set_team.assert_not_called()


async def test_create_without_head_does_not_touch_any_member(
    service: DepartmentService, repo: AsyncMock, members: AsyncMock
) -> None:
    p = _principal()
    repo.create.return_value = _dept(p.workspace_id)
    await service.create(CreateDepartmentRequest(name="Eng"), p)
    members.set_team.assert_not_called()


async def test_update_without_head_change_does_not_touch_member_team(
    service: DepartmentService, repo: AsyncMock, members: AsyncMock
) -> None:
    """Renaming the department leaves the (existing) head alone."""
    p = _principal()
    existing_head = _member(p.workspace_id, name="Alice")
    existing = _dept(p.workspace_id, head_id=existing_head.id)
    repo.get_by_id.return_value = existing
    repo.update.return_value = _dept(p.workspace_id, head_id=existing_head.id)
    # The service resolves the head summary for the response even when
    # the PATCH didn't touch head_id; return the real Member so that
    # path doesn't trip pydantic on AsyncMock placeholders.
    members.get_by_id.return_value = existing_head

    await service.update(existing.id, UpdateDepartmentRequest(name="Eng2"), p)
    members.set_team.assert_not_called()
