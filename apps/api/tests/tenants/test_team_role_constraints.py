"""Single-MANAGER / single-LEAD enforcement + auto-demotion + department
resolution on the set-member-team flow.

Contract:
- A team has at most ONE MANAGER and at most ONE LEAD.
- When an admin assigns the MANAGER (or LEAD) role to user X on team T
  and another member Y currently holds that role on T, Y is demoted to
  MEMBER in the same DB transaction before X is upgraded.
- Reassigning MEMBER does not trigger a demotion (multiple MEMBERs are
  allowed).
- Reassigning the SAME user to the SAME role is a no-op for the
  demotion check (the function doesn't demote the target itself).
- The PATCH response carries the resolved department for the new team
  (so the UI can render the new hierarchy without a follow-up call).
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.application.tasks.schemas import Principal
from app.application.tenants.schemas import SetMemberTeamRequest
from app.application.tenants.service import InviteService
from app.domain.entities import Department, Member, Team
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
    name: str = "Alice",
    team_id=None,
    team_role: TeamRole | None = None,
) -> Member:
    return Member(
        id=uuid4(),
        workspace_id=workspace_id,
        type=MemberType.HUMAN,
        name=name,
        email=f"{name.lower()}@example.com",
        priority=3,
        role=MemberRole.WORKSPACE_USER,
        team_id=team_id,
        team_role=team_role,
    )


def _team(workspace_id, *, department_id=None) -> Team:
    now = datetime.now(UTC)
    return Team(
        id=uuid4(),
        workspace_id=workspace_id,
        name="Backend",
        department_id=department_id,
        created_at=now,
        updated_at=now,
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


@pytest.fixture
def invites_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def members_repo() -> AsyncMock:
    r = AsyncMock()
    # Default: no current holder for any role — overridden per-test.
    r.get_for_team_role.return_value = None
    return r


@pytest.fixture
def workspaces_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def teams_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def departments_repo() -> AsyncMock:
    r = AsyncMock()
    # No member heads any department by default — these tests don't
    # exercise the dept-head isolation / inheritance paths, so the
    # short-circuit keeps them green.
    r.get_for_head.return_value = None
    return r


@pytest.fixture
def auth_members() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(
    invites_repo: AsyncMock,
    members_repo: AsyncMock,
    workspaces_repo: AsyncMock,
    teams_repo: AsyncMock,
    departments_repo: AsyncMock,
    auth_members: AsyncMock,
) -> InviteService:
    return InviteService(
        invites=invites_repo,
        members=members_repo,
        workspaces=workspaces_repo,
        auth_members=auth_members,
        credentials=AsyncMock(),
        hasher=AsyncMock(),
        tokens=AsyncMock(),
        accept_url_base="http://example",
        teams=teams_repo,
        departments=departments_repo,
    )


async def test_assigning_manager_demotes_existing_manager(
    service: InviteService,
    members_repo: AsyncMock,
    teams_repo: AsyncMock,
) -> None:
    p = _principal(role=MemberRole.WORKSPACE_ADMIN)
    team = _team(p.workspace_id)
    target = _member(p.workspace_id, name="Alice")
    sitting_manager = _member(
        p.workspace_id, name="Bob", team_id=team.id, team_role=TeamRole.MANAGER
    )
    members_repo.get_by_id.return_value = target
    teams_repo.get_by_id.return_value = team
    members_repo.get_for_team_role.return_value = sitting_manager

    members_repo.set_team.side_effect = lambda _id, **kw: target

    await service.set_member_team(
        target.id,
        SetMemberTeamRequest(team_id=team.id, team_role=TeamRole.MANAGER),
        p,
    )

    # Existing manager Bob is demoted (kept on the team but role=MEMBER)
    # BEFORE the target is promoted, all on the same session.
    set_team_calls = members_repo.set_team.await_args_list
    assert any(
        call.args == (sitting_manager.id,)
        and call.kwargs == {"team_id": team.id, "team_role": TeamRole.MEMBER}
        for call in set_team_calls
    ), set_team_calls
    assert any(
        call.args == (target.id,)
        and call.kwargs == {"team_id": team.id, "team_role": TeamRole.MANAGER}
        for call in set_team_calls
    ), set_team_calls


async def test_assigning_lead_demotes_existing_lead(
    service: InviteService,
    members_repo: AsyncMock,
    teams_repo: AsyncMock,
) -> None:
    p = _principal(role=MemberRole.WORKSPACE_ADMIN)
    team = _team(p.workspace_id)
    target = _member(p.workspace_id, name="Alice")
    sitting_lead = _member(p.workspace_id, name="Bob", team_id=team.id, team_role=TeamRole.LEAD)
    members_repo.get_by_id.return_value = target
    teams_repo.get_by_id.return_value = team
    members_repo.get_for_team_role.return_value = sitting_lead
    members_repo.set_team.side_effect = lambda _id, **kw: target

    await service.set_member_team(
        target.id,
        SetMemberTeamRequest(team_id=team.id, team_role=TeamRole.LEAD),
        p,
    )
    members_repo.get_for_team_role.assert_awaited_once_with(team.id, TeamRole.LEAD)
    set_team_calls = members_repo.set_team.await_args_list
    assert any(
        call.kwargs == {"team_id": team.id, "team_role": TeamRole.MEMBER}
        and call.args == (sitting_lead.id,)
        for call in set_team_calls
    )


async def test_assigning_manager_does_not_demote_lead(
    service: InviteService,
    members_repo: AsyncMock,
    teams_repo: AsyncMock,
) -> None:
    """The constraint is per-role: a new MANAGER doesn't affect the
    sitting LEAD."""
    p = _principal(role=MemberRole.WORKSPACE_ADMIN)
    team = _team(p.workspace_id)
    target = _member(p.workspace_id, name="Alice")
    members_repo.get_by_id.return_value = target
    teams_repo.get_by_id.return_value = team
    members_repo.get_for_team_role.return_value = None
    members_repo.set_team.side_effect = lambda _id, **kw: target

    await service.set_member_team(
        target.id,
        SetMemberTeamRequest(team_id=team.id, team_role=TeamRole.MANAGER),
        p,
    )
    # Only the MANAGER slot is checked, not LEAD.
    members_repo.get_for_team_role.assert_awaited_once_with(team.id, TeamRole.MANAGER)


async def test_assigning_member_role_skips_demotion_check(
    service: InviteService,
    members_repo: AsyncMock,
    teams_repo: AsyncMock,
) -> None:
    """Plural MEMBERs are allowed — no constraint, no lookup."""
    p = _principal(role=MemberRole.WORKSPACE_ADMIN)
    team = _team(p.workspace_id)
    target = _member(p.workspace_id, name="Alice")
    members_repo.get_by_id.return_value = target
    teams_repo.get_by_id.return_value = team
    members_repo.set_team.side_effect = lambda _id, **kw: target

    await service.set_member_team(
        target.id,
        SetMemberTeamRequest(team_id=team.id, team_role=TeamRole.MEMBER),
        p,
    )
    members_repo.get_for_team_role.assert_not_called()


async def test_self_reassignment_to_same_role_does_not_demote_self(
    service: InviteService,
    members_repo: AsyncMock,
    teams_repo: AsyncMock,
) -> None:
    """If user X is already MANAGER on T and admin sets MANAGER on T
    again, the 'existing holder' lookup IS the target — don't demote
    them just to immediately re-promote."""
    p = _principal(role=MemberRole.WORKSPACE_ADMIN)
    team = _team(p.workspace_id)
    target = _member(p.workspace_id, name="Alice", team_id=team.id, team_role=TeamRole.MANAGER)
    members_repo.get_by_id.return_value = target
    teams_repo.get_by_id.return_value = team
    members_repo.get_for_team_role.return_value = target
    members_repo.set_team.side_effect = lambda _id, **kw: target

    await service.set_member_team(
        target.id,
        SetMemberTeamRequest(team_id=team.id, team_role=TeamRole.MANAGER),
        p,
    )
    # We should NOT see a "demote the target to MEMBER" call.
    for call in members_repo.set_team.await_args_list:
        if call.args == (target.id,):
            assert call.kwargs["team_role"] == TeamRole.MANAGER


async def test_response_includes_resolved_department(
    service: InviteService,
    members_repo: AsyncMock,
    teams_repo: AsyncMock,
    departments_repo: AsyncMock,
) -> None:
    p = _principal(role=MemberRole.WORKSPACE_ADMIN)
    dept = _dept(p.workspace_id)
    team = _team(p.workspace_id, department_id=dept.id)
    target = _member(p.workspace_id, name="Alice")
    after = _member(p.workspace_id, name="Alice", team_id=team.id, team_role=TeamRole.MEMBER)

    members_repo.get_by_id.return_value = target
    teams_repo.get_by_id.return_value = team
    departments_repo.get_by_id.return_value = dept
    members_repo.set_team.side_effect = lambda _id, **kw: after

    result = await service.set_member_team(
        target.id,
        SetMemberTeamRequest(team_id=team.id, team_role=TeamRole.MEMBER),
        p,
    )

    assert result.department is not None
    assert result.department.id == dept.id
    assert result.department.name == dept.name


async def test_response_has_null_department_when_team_has_none(
    service: InviteService,
    members_repo: AsyncMock,
    teams_repo: AsyncMock,
    departments_repo: AsyncMock,
) -> None:
    p = _principal(role=MemberRole.WORKSPACE_ADMIN)
    team = _team(p.workspace_id, department_id=None)  # un-filed team
    target = _member(p.workspace_id)
    after = _member(p.workspace_id, team_id=team.id, team_role=TeamRole.MEMBER)
    members_repo.get_by_id.return_value = target
    teams_repo.get_by_id.return_value = team
    members_repo.set_team.side_effect = lambda _id, **kw: after

    result = await service.set_member_team(
        target.id,
        SetMemberTeamRequest(team_id=team.id, team_role=TeamRole.MEMBER),
        p,
    )
    assert result.department is None
    departments_repo.get_by_id.assert_not_called()


async def test_response_has_null_department_when_unassigned(
    service: InviteService,
    members_repo: AsyncMock,
    teams_repo: AsyncMock,
    departments_repo: AsyncMock,
) -> None:
    p = _principal(role=MemberRole.WORKSPACE_ADMIN)
    target = _member(p.workspace_id, team_id=uuid4(), team_role=TeamRole.MEMBER)
    after = _member(p.workspace_id, team_id=None, team_role=None)
    members_repo.get_by_id.return_value = target
    members_repo.set_team.side_effect = lambda _id, **kw: after

    result = await service.set_member_team(target.id, SetMemberTeamRequest(), p)
    assert result.department is None
    departments_repo.get_by_id.assert_not_called()
