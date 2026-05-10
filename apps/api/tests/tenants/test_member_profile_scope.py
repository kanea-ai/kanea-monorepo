"""Tests for the priority-scoped profile lookup
(GET /api/v1/tenants/members/{id}/profile via
``InviteService.get_member_profile``).

Drives the audit-log "click the actor" flow: a lower-rank admin
opening a higher-rank member's profile gets the limited shape
(id / name / email / type only).
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.application.tasks.schemas import Principal
from app.application.tenants.service import InviteService
from app.domain.entities import Member
from app.domain.enums import MemberRole, MemberType


def _principal(
    *,
    role: MemberRole = MemberRole.WORKSPACE_ADMIN,
    priority: int = 5,
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


def _member(workspace_id, *, priority: int = 1, member_id=None) -> Member:
    now = datetime.now(UTC)
    return Member(
        id=member_id or uuid4(),
        workspace_id=workspace_id,
        type=MemberType.HUMAN,
        name="Alice",
        email="a@example.com",
        priority=priority,
        role=MemberRole.WORKSPACE_OWNER,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def members_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(members_repo: AsyncMock) -> InviteService:
    return InviteService(
        invites=AsyncMock(),
        members=members_repo,
        workspaces=AsyncMock(),
        auth_members=AsyncMock(),
        credentials=AsyncMock(),
        hasher=AsyncMock(),
        tokens=AsyncMock(),
        accept_url_base="http://example",
    )


# ---------- full view paths ----------


async def test_owner_always_gets_full_view(service: InviteService, members_repo: AsyncMock) -> None:
    p = _principal(role=MemberRole.WORKSPACE_OWNER, priority=1)
    target = _member(p.workspace_id, priority=2)
    members_repo.get_by_id.return_value = target
    profile = await service.get_member_profile(target.id, p)
    assert profile.is_limited_view is False
    assert profile.role is target.role
    assert profile.priority == target.priority


async def test_self_always_gets_full_view(service: InviteService, members_repo: AsyncMock) -> None:
    """Even a high-priority-number admin can see their own role."""
    p = _principal(role=MemberRole.WORKSPACE_ADMIN, priority=10)
    self_member = _member(p.workspace_id, priority=10, member_id=p.member_id)
    members_repo.get_by_id.return_value = self_member
    profile = await service.get_member_profile(self_member.id, p)
    assert profile.is_limited_view is False


async def test_higher_rank_admin_sees_full_view(
    service: InviteService, members_repo: AsyncMock
) -> None:
    """Principal priority ≤ target priority → full view (principal is
    rank-equal or higher than target)."""
    p = _principal(role=MemberRole.WORKSPACE_ADMIN, priority=2)
    target = _member(p.workspace_id, priority=4)  # lower-rank target
    members_repo.get_by_id.return_value = target
    profile = await service.get_member_profile(target.id, p)
    assert profile.is_limited_view is False


# ---------- limited view path ----------


async def test_lower_rank_admin_sees_limited_view(
    service: InviteService, members_repo: AsyncMock
) -> None:
    """Principal priority > target priority → limited view (principal
    is lower-rank than target). Only id/name/email/type populated."""
    p = _principal(role=MemberRole.WORKSPACE_ADMIN, priority=4)
    target = _member(p.workspace_id, priority=2)  # higher-rank target
    members_repo.get_by_id.return_value = target

    profile = await service.get_member_profile(target.id, p)

    assert profile.is_limited_view is True
    assert profile.id == target.id
    assert profile.name == target.name
    assert profile.email == target.email
    # Restricted fields stripped.
    assert profile.role is None
    assert profile.priority is None
    assert profile.team_id is None
    assert profile.team_role is None
    assert profile.is_suspended is None
