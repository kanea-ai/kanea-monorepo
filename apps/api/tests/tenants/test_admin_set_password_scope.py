"""Tests for the admin password-reset scope matrix.

Phase 6 follow-up: an admin can reset a member's password only when
they share organisational scope (same team OR same department). An
owner has no such constraint — they can reset anyone non-self,
non-agent, non-cross-workspace.

We verify each cell of the matrix against
``InviteService.admin_set_member_password``:
- Owner happy path
- Admin same-team allowed
- Admin same-department (cross-team) allowed
- Admin different-dept-and-team forbidden
- Admin can't reset an OWNER target
- Cross-workspace user is always forbidden
- Self-reset is rejected
- Agent target is rejected
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.application.tasks.schemas import Principal
from app.application.tenants.service import InviteService
from app.domain.entities import Member, Team
from app.domain.enums import MemberRole, MemberType
from app.domain.exceptions import (
    ForbiddenError,
    InvalidMemberTypeError,
)


def _principal(
    *,
    role: MemberRole = MemberRole.WORKSPACE_ADMIN,
    member_id: UUID | None = None,
    workspace_id: UUID | None = None,
) -> Principal:
    return Principal(
        member_id=member_id or uuid4(),
        workspace_id=workspace_id or uuid4(),
        type=MemberType.HUMAN,
        priority=2,
        scope="human",
        role=role,
    )


def _member(
    *,
    workspace_id: UUID,
    member_id: UUID | None = None,
    user_id: UUID | None = None,
    team_id: UUID | None = None,
    role: MemberRole = MemberRole.WORKSPACE_USER,
) -> Member:
    now = datetime.now(UTC)
    return Member(
        id=member_id or uuid4(),
        workspace_id=workspace_id,
        type=MemberType.HUMAN,
        name="alice",
        email="a@example.com",
        priority=5,
        role=role,
        user_id=user_id or uuid4(),
        team_id=team_id,
        created_at=now,
        updated_at=now,
    )


def _team(workspace_id: UUID, *, department_id: UUID | None = None) -> Team:
    now = datetime.now(UTC)
    return Team(
        id=uuid4(),
        workspace_id=workspace_id,
        name="Backend",
        department_id=department_id,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def members_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def auth_members() -> AsyncMock:
    """Auth-side member repo. ``list_for_user`` drives the cross-
    workspace check; default to a single membership so the happy
    paths don't have to wire it themselves."""
    repo = AsyncMock()
    repo.list_for_user.return_value = [
        # Single membership stub — list contains one row, len > 1 is
        # the failing case.
        Member(
            id=uuid4(),
            workspace_id=uuid4(),
            type=MemberType.HUMAN,
            name="x",
            email="x@x",
            priority=5,
        )
    ]
    return repo


@pytest.fixture
def teams_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def users() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def hasher() -> MagicMock:
    h = MagicMock()
    h.hash.side_effect = lambda raw: f"bcrypt${raw}"
    return h


@pytest.fixture
def service(
    members_repo: AsyncMock,
    auth_members: AsyncMock,
    teams_repo: AsyncMock,
    users: AsyncMock,
    hasher: MagicMock,
) -> InviteService:
    return InviteService(
        invites=AsyncMock(),
        members=members_repo,
        workspaces=AsyncMock(),
        auth_members=auth_members,
        credentials=AsyncMock(),
        hasher=hasher,
        tokens=AsyncMock(),
        accept_url_base="http://example",
        users=users,
        teams=teams_repo,
    )


# ---------- owner happy path ----------


async def test_owner_can_reset_anyone_non_self(
    service: InviteService,
    members_repo: AsyncMock,
    users: AsyncMock,
) -> None:
    """No scope check — owners are top of the access tree."""
    p = _principal(role=MemberRole.WORKSPACE_OWNER)
    target = _member(workspace_id=p.workspace_id)
    members_repo.get_by_id.return_value = target
    await service.admin_set_member_password(target.id, "supersecret123", p)
    users.update_password.assert_awaited_once()


async def test_owner_can_reset_admin(
    service: InviteService,
    members_repo: AsyncMock,
    users: AsyncMock,
) -> None:
    p = _principal(role=MemberRole.WORKSPACE_OWNER)
    target = _member(workspace_id=p.workspace_id, role=MemberRole.WORKSPACE_ADMIN)
    members_repo.get_by_id.return_value = target
    await service.admin_set_member_password(target.id, "supersecret123", p)
    users.update_password.assert_awaited_once()


# ---------- admin same-team allowed ----------


async def test_admin_can_reset_same_team_member(
    service: InviteService,
    members_repo: AsyncMock,
    users: AsyncMock,
) -> None:
    p = _principal(role=MemberRole.WORKSPACE_ADMIN)
    team_id = uuid4()
    admin_self = _member(workspace_id=p.workspace_id, member_id=p.member_id, team_id=team_id)
    target = _member(workspace_id=p.workspace_id, team_id=team_id)
    # The repo serves both lookups: target_id → target, principal.member_id → admin_self.
    members_repo.get_by_id.side_effect = lambda mid: (
        target if mid == target.id else admin_self if mid == p.member_id else None
    )

    await service.admin_set_member_password(target.id, "supersecret123", p)
    users.update_password.assert_awaited_once()


# ---------- admin same-department (cross-team) allowed ----------


async def test_admin_can_reset_same_department_cross_team(
    service: InviteService,
    members_repo: AsyncMock,
    teams_repo: AsyncMock,
    users: AsyncMock,
) -> None:
    """Admin and target are on *different* teams, but those teams
    share a department_id. Allowed."""
    p = _principal(role=MemberRole.WORKSPACE_ADMIN)
    department_id = uuid4()
    admin_team = _team(p.workspace_id, department_id=department_id)
    target_team = _team(p.workspace_id, department_id=department_id)
    admin_self = _member(workspace_id=p.workspace_id, member_id=p.member_id, team_id=admin_team.id)
    target = _member(workspace_id=p.workspace_id, team_id=target_team.id)

    members_repo.get_by_id.side_effect = lambda mid: (
        target if mid == target.id else admin_self if mid == p.member_id else None
    )
    teams_repo.get_by_id.side_effect = lambda tid: (
        admin_team if tid == admin_team.id else target_team if tid == target_team.id else None
    )

    await service.admin_set_member_password(target.id, "supersecret123", p)
    users.update_password.assert_awaited_once()


# ---------- admin different scope forbidden ----------


async def test_admin_cannot_reset_unrelated_member(
    service: InviteService,
    members_repo: AsyncMock,
    teams_repo: AsyncMock,
    users: AsyncMock,
) -> None:
    """Different team AND different department → forbidden."""
    p = _principal(role=MemberRole.WORKSPACE_ADMIN)
    admin_team = _team(p.workspace_id, department_id=uuid4())
    target_team = _team(p.workspace_id, department_id=uuid4())
    admin_self = _member(workspace_id=p.workspace_id, member_id=p.member_id, team_id=admin_team.id)
    target = _member(workspace_id=p.workspace_id, team_id=target_team.id)

    members_repo.get_by_id.side_effect = lambda mid: (
        target if mid == target.id else admin_self if mid == p.member_id else None
    )
    teams_repo.get_by_id.side_effect = lambda tid: (
        admin_team if tid == admin_team.id else target_team if tid == target_team.id else None
    )

    with pytest.raises(ForbiddenError, match="team or department"):
        await service.admin_set_member_password(target.id, "supersecret123", p)
    users.update_password.assert_not_called()


async def test_admin_with_no_team_cannot_reset_others(
    service: InviteService,
    members_repo: AsyncMock,
    users: AsyncMock,
) -> None:
    """Admin without a team has no org scope — only owners can act
    workspace-wide."""
    p = _principal(role=MemberRole.WORKSPACE_ADMIN)
    admin_self = _member(workspace_id=p.workspace_id, member_id=p.member_id, team_id=None)
    target = _member(workspace_id=p.workspace_id, team_id=uuid4())
    members_repo.get_by_id.side_effect = lambda mid: (
        target if mid == target.id else admin_self if mid == p.member_id else None
    )

    with pytest.raises(ForbiddenError):
        await service.admin_set_member_password(target.id, "supersecret123", p)
    users.update_password.assert_not_called()


# ---------- admin can't reset an OWNER ----------


async def test_admin_cannot_reset_owner(
    service: InviteService,
    members_repo: AsyncMock,
    users: AsyncMock,
) -> None:
    p = _principal(role=MemberRole.WORKSPACE_ADMIN)
    team_id = uuid4()
    admin_self = _member(workspace_id=p.workspace_id, member_id=p.member_id, team_id=team_id)
    target_owner = _member(
        workspace_id=p.workspace_id, team_id=team_id, role=MemberRole.WORKSPACE_OWNER
    )
    members_repo.get_by_id.side_effect = lambda mid: (
        target_owner if mid == target_owner.id else admin_self if mid == p.member_id else None
    )

    with pytest.raises(ForbiddenError, match="owner"):
        await service.admin_set_member_password(target_owner.id, "supersecret123", p)
    users.update_password.assert_not_called()


# ---------- shared-rule guards ----------


async def test_self_reset_rejected_for_owners_too(
    service: InviteService,
    members_repo: AsyncMock,
    users: AsyncMock,
) -> None:
    """Even owners can't shortcut /me/password — that endpoint
    requires the current password as belt-and-braces."""
    p = _principal(role=MemberRole.WORKSPACE_OWNER)
    self_member = _member(workspace_id=p.workspace_id, member_id=p.member_id)
    members_repo.get_by_id.return_value = self_member

    with pytest.raises(ForbiddenError, match="/me"):
        await service.admin_set_member_password(p.member_id, "abcdefgh", p)
    users.update_password.assert_not_called()


async def test_agent_target_rejected(
    service: InviteService,
    members_repo: AsyncMock,
    users: AsyncMock,
) -> None:
    """Agents have no User row; password doesn't apply."""
    p = _principal(role=MemberRole.WORKSPACE_OWNER)
    target = Member(
        id=uuid4(),
        workspace_id=p.workspace_id,
        type=MemberType.AGENT,
        name="bot",
        email=None,
        priority=5,
        role=MemberRole.WORKSPACE_USER,
        user_id=None,
    )
    members_repo.get_by_id.return_value = target

    with pytest.raises(InvalidMemberTypeError, match="agents"):
        await service.admin_set_member_password(target.id, "abcdefgh", p)
    users.update_password.assert_not_called()


async def test_cross_workspace_user_rejected(
    service: InviteService,
    members_repo: AsyncMock,
    auth_members: AsyncMock,
    users: AsyncMock,
) -> None:
    """A user with memberships in other workspaces can't be reset by
    this workspace's owner — that credential is shared."""
    p = _principal(role=MemberRole.WORKSPACE_OWNER)
    target = _member(workspace_id=p.workspace_id)
    members_repo.get_by_id.return_value = target
    # Two memberships → cross-workspace.
    auth_members.list_for_user.return_value = [
        Member(
            id=uuid4(),
            workspace_id=p.workspace_id,
            type=MemberType.HUMAN,
            name="t",
            email="t@t",
            priority=5,
        ),
        Member(
            id=uuid4(),
            workspace_id=uuid4(),
            type=MemberType.HUMAN,
            name="t",
            email="t@t",
            priority=5,
        ),
    ]

    with pytest.raises(ForbiddenError, match="other workspaces"):
        await service.admin_set_member_password(target.id, "abcdefgh", p)
    users.update_password.assert_not_called()
