"""Phase 5 batch 3 — dashboard RBAC scoping.

Five role tiers, each producing a different repo call:
- ADMIN/OWNER: no narrowing (workspace-wide).
- HEAD/MANAGER on a team: project-set across the team's projects
  PLUS the team itself.
- LEAD on a team: team-only.
- MEMBER on a team: self + team.
- No team and not admin: self only.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.application.me.service import MeService
from app.application.tasks.schemas import Principal
from app.domain.entities import Member, Workspace
from app.domain.enums import MemberRole, MemberType, TeamRole


def _principal(*, member_id=None, workspace_id=None, role=MemberRole.WORKSPACE_USER) -> Principal:
    return Principal(
        member_id=member_id or uuid4(),
        workspace_id=workspace_id or uuid4(),
        type=MemberType.HUMAN,
        priority=5,
        scope="human",
        role=role,
    )


def _member(
    *,
    member_id,
    workspace_id,
    user_id=None,
    team_id=None,
    team_role=None,
) -> Member:
    now = datetime.now(UTC)
    return Member(
        id=member_id,
        workspace_id=workspace_id,
        type=MemberType.HUMAN,
        name="Test",
        priority=5,
        user_id=user_id or uuid4(),
        team_id=team_id,
        team_role=team_role,
        role=MemberRole.WORKSPACE_USER,
        created_at=now,
        updated_at=now,
    )


def _workspace(workspace_id) -> Workspace:
    now = datetime.now(UTC)
    return Workspace(
        id=workspace_id,
        name="Acme",
        slug="acme",
        task_prefix="ACME",
        next_task_seq=1,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def deps() -> tuple[MeService, AsyncMock, AsyncMock, AsyncMock, MagicMock, AsyncMock]:
    users = AsyncMock()
    members = AsyncMock()
    workspaces = AsyncMock()
    hasher = MagicMock()
    tasks = AsyncMock()
    tasks.list_for_dashboard.return_value = []
    tasks.list_project_ids_for_team.return_value = []
    svc = MeService(
        users=users,
        members=members,
        workspaces=workspaces,
        hasher=hasher,
        tasks=tasks,
    )
    return svc, users, members, workspaces, hasher, tasks


async def test_admin_sees_workspace_wide(
    deps: tuple[MeService, AsyncMock, AsyncMock, AsyncMock, MagicMock, AsyncMock],
) -> None:
    svc, _u, members, workspaces, _h, tasks = deps
    p = _principal(role=MemberRole.WORKSPACE_OWNER)
    members.get_by_id.return_value = _member(member_id=p.member_id, workspace_id=p.workspace_id)
    workspaces.get_by_id.return_value = _workspace(p.workspace_id)

    out = await svc.get_dashboard(p)
    assert out.scope.is_admin is True
    assert out.scope.label == "Workspace"
    # No narrowing kwargs — admin path passes nothing through.
    tasks.list_for_dashboard.assert_awaited_once_with(p.workspace_id)


async def test_manager_sees_team_plus_projects(
    deps: tuple[MeService, AsyncMock, AsyncMock, AsyncMock, MagicMock, AsyncMock],
) -> None:
    svc, _u, members, workspaces, _h, tasks = deps
    p = _principal(role=MemberRole.WORKSPACE_USER)
    team_id = uuid4()
    members.get_by_id.return_value = _member(
        member_id=p.member_id,
        workspace_id=p.workspace_id,
        team_id=team_id,
        team_role=TeamRole.MANAGER,
    )
    workspaces.get_by_id.return_value = _workspace(p.workspace_id)
    project_a, project_b = uuid4(), uuid4()
    tasks.list_project_ids_for_team.return_value = [project_a, project_b]

    out = await svc.get_dashboard(p)
    assert out.scope.is_admin is False
    assert out.scope.label == "Projects you oversee"
    assert out.scope.team_id == team_id
    assert out.scope.project_count == 2
    tasks.list_project_ids_for_team.assert_awaited_once_with(p.workspace_id, team_id)
    tasks.list_for_dashboard.assert_awaited_once_with(
        p.workspace_id,
        team_id=team_id,
        project_ids=[project_a, project_b],
    )


async def test_head_treated_as_manager(
    deps: tuple[MeService, AsyncMock, AsyncMock, AsyncMock, MagicMock, AsyncMock],
) -> None:
    """HEAD is the team's top — same projects-scoped view as MANAGER."""
    svc, _u, members, workspaces, _h, tasks = deps
    p = _principal()
    team_id = uuid4()
    members.get_by_id.return_value = _member(
        member_id=p.member_id,
        workspace_id=p.workspace_id,
        team_id=team_id,
        team_role=TeamRole.HEAD,
    )
    workspaces.get_by_id.return_value = _workspace(p.workspace_id)
    tasks.list_project_ids_for_team.return_value = [uuid4()]

    out = await svc.get_dashboard(p)
    assert out.scope.label == "Projects you oversee"
    tasks.list_project_ids_for_team.assert_awaited_once()


async def test_lead_team_only(
    deps: tuple[MeService, AsyncMock, AsyncMock, AsyncMock, MagicMock, AsyncMock],
) -> None:
    svc, _u, members, workspaces, _h, tasks = deps
    p = _principal()
    team_id = uuid4()
    members.get_by_id.return_value = _member(
        member_id=p.member_id,
        workspace_id=p.workspace_id,
        team_id=team_id,
        team_role=TeamRole.LEAD,
    )
    workspaces.get_by_id.return_value = _workspace(p.workspace_id)

    out = await svc.get_dashboard(p)
    assert out.scope.label == "Your team"
    assert out.scope.team_id == team_id
    tasks.list_for_dashboard.assert_awaited_once_with(p.workspace_id, team_id=team_id)
    # LEAD doesn't pull projects — that's the manager scope.
    tasks.list_project_ids_for_team.assert_not_awaited()


async def test_member_self_plus_team(
    deps: tuple[MeService, AsyncMock, AsyncMock, AsyncMock, MagicMock, AsyncMock],
) -> None:
    svc, _u, members, workspaces, _h, tasks = deps
    p = _principal()
    team_id = uuid4()
    members.get_by_id.return_value = _member(
        member_id=p.member_id,
        workspace_id=p.workspace_id,
        team_id=team_id,
        team_role=TeamRole.MEMBER,
    )
    workspaces.get_by_id.return_value = _workspace(p.workspace_id)

    out = await svc.get_dashboard(p)
    assert out.scope.label == "You + your team"
    assert out.scope.member_id == p.member_id
    assert out.scope.team_id == team_id
    tasks.list_for_dashboard.assert_awaited_once_with(
        p.workspace_id, member_id=p.member_id, team_id=team_id
    )


async def test_no_team_self_only(
    deps: tuple[MeService, AsyncMock, AsyncMock, AsyncMock, MagicMock, AsyncMock],
) -> None:
    svc, _u, members, workspaces, _h, tasks = deps
    p = _principal()
    members.get_by_id.return_value = _member(
        member_id=p.member_id, workspace_id=p.workspace_id, team_id=None
    )
    workspaces.get_by_id.return_value = _workspace(p.workspace_id)

    out = await svc.get_dashboard(p)
    assert out.scope.label == "Your tasks"
    assert out.scope.member_id == p.member_id
    assert out.scope.team_id is None
    tasks.list_for_dashboard.assert_awaited_once_with(p.workspace_id, member_id=p.member_id)
