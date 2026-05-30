"""Strict Department-Head hierarchy isolation + RBAC inheritance.

Two contracts under one suite:

1. **Isolation** — once a member is promoted to ``departments.head_id``,
   the api refuses to assign them to a Team via ``set_member_team``. An
   explicit unassign (``team_id=null``) is still allowed (matches the
   clearing path used by DepartmentService when the head is set in the
   first place).

2. **Inheritance** — a Department Head is implicitly granted MANAGER-
   level reach over EVERY team filed under their department. The two
   member-management surfaces this affects are:
     * ``set_member_team`` — head can move members into / out of the
       teams under their department, without an explicit admin role.
     * ``admin_set_member_password`` — head can reset the password of
       any human member sitting on those teams.
   In both cases the head's reach stops at the department boundary —
   touching a team in OTHER department raises ``ForbiddenError``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from app.application.tasks.schemas import Principal
from app.application.tenants.schemas import SetMemberTeamRequest
from app.application.tenants.service import InviteService
from app.domain.entities import Department, Member, Team, User
from app.domain.enums import MemberRole, MemberType, TeamRole
from app.domain.exceptions import (
    ForbiddenError,
    InvalidMemberTypeError,
    MemberIsDepartmentHeadError,
)

# ---------- factories ----------


def _principal(
    *,
    role: MemberRole = MemberRole.WORKSPACE_USER,
    member_id: UUID | None = None,
    workspace_id: UUID | None = None,
    priority: int = 3,
) -> Principal:
    return Principal(
        member_id=member_id or uuid4(),
        workspace_id=workspace_id or uuid4(),
        type=MemberType.HUMAN,
        priority=priority,
        scope="human",
        role=role,
    )


def _member(
    workspace_id: UUID,
    *,
    member_id: UUID | None = None,
    user_id: UUID | None = None,
    name: str = "Alice",
    team_id: UUID | None = None,
    team_role: TeamRole | None = None,
    role: MemberRole = MemberRole.WORKSPACE_USER,
) -> Member:
    return Member(
        id=member_id or uuid4(),
        workspace_id=workspace_id,
        type=MemberType.HUMAN,
        name=name,
        email=f"{name.lower()}@example.com",
        priority=5,
        role=role,
        user_id=user_id or uuid4(),
        team_id=team_id,
        team_role=team_role,
    )


def _team(
    workspace_id: UUID, *, team_id: UUID | None = None, department_id: UUID | None = None
) -> Team:
    now = datetime.now(UTC)
    return Team(
        id=team_id or uuid4(),
        workspace_id=workspace_id,
        name="Backend",
        department_id=department_id,
        created_at=now,
        updated_at=now,
    )


def _dept(
    workspace_id: UUID, *, dept_id: UUID | None = None, head_id: UUID | None = None
) -> Department:
    now = datetime.now(UTC)
    return Department(
        id=dept_id or uuid4(),
        workspace_id=workspace_id,
        name="Engineering",
        description=None,
        head_id=head_id,
        created_at=now,
        updated_at=now,
    )


# ---------- fixtures ----------


@pytest.fixture
def members_repo() -> AsyncMock:
    r = AsyncMock()
    r.get_for_team_role.return_value = None
    return r


@pytest.fixture
def teams_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def departments_repo() -> AsyncMock:
    r = AsyncMock()
    # No member heads any department by default; tests override.
    r.get_for_head.return_value = None
    return r


@pytest.fixture
def auth_members() -> AsyncMock:
    r = AsyncMock()
    # Single membership default — the password-reset cross-workspace
    # guard short-circuits to the org-scope check.
    r.list_for_user.return_value = [
        Member(
            id=uuid4(),
            workspace_id=uuid4(),
            type=MemberType.HUMAN,
            name="x",
            email="x@x",
            priority=5,
        )
    ]
    return r


@pytest.fixture
def users_repo() -> AsyncMock:
    r = AsyncMock()
    r.update_password.return_value = User(
        id=uuid4(),
        email="x@x",
        full_name="x",
        password_hash="h",
    )
    return r


@pytest.fixture
def hasher() -> AsyncMock:
    h = AsyncMock()
    h.hash.return_value = "hashed"
    return h


@pytest.fixture
def service(
    members_repo: AsyncMock,
    teams_repo: AsyncMock,
    departments_repo: AsyncMock,
    auth_members: AsyncMock,
    users_repo: AsyncMock,
    hasher: AsyncMock,
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
        teams=teams_repo,
        users=users_repo,
        departments=departments_repo,
    )


# ===========================================================================
# Strict isolation: set_member_team refuses to put a dept head on a team.
# ===========================================================================


async def test_set_member_team_refuses_assignment_when_target_is_dept_head(
    service: InviteService,
    members_repo: AsyncMock,
    teams_repo: AsyncMock,
    departments_repo: AsyncMock,
) -> None:
    p = _principal(role=MemberRole.WORKSPACE_ADMIN, priority=1)
    workspace = p.workspace_id
    team = _team(workspace)
    target = _member(workspace, name="Bob")
    head_dept = _dept(workspace, head_id=target.id)

    members_repo.get_by_id.return_value = target
    teams_repo.get_by_id.return_value = team
    departments_repo.get_for_head.return_value = head_dept

    with pytest.raises(MemberIsDepartmentHeadError):
        await service.set_member_team(
            target.id,
            SetMemberTeamRequest(team_id=team.id, team_role=TeamRole.MEMBER),
            p,
        )
    members_repo.set_team.assert_not_called()


async def test_set_member_team_allows_unassign_for_dept_head(
    service: InviteService,
    members_repo: AsyncMock,
    departments_repo: AsyncMock,
) -> None:
    """``team_id=null`` is the explicit clear path used by
    DepartmentService when the member is first promoted to head. It must
    keep working AFTER that promotion (e.g. the DepartmentService
    re-saves the same head). Refusal only applies to non-null
    assignments."""
    p = _principal(role=MemberRole.WORKSPACE_ADMIN, priority=1)
    workspace = p.workspace_id
    target = _member(workspace, name="Bob", team_id=None, team_role=None)
    head_dept = _dept(workspace, head_id=target.id)

    members_repo.get_by_id.return_value = target
    departments_repo.get_for_head.return_value = head_dept
    members_repo.set_team.side_effect = lambda _id, **kw: target

    await service.set_member_team(target.id, SetMemberTeamRequest(), p)
    members_repo.set_team.assert_awaited_once_with(target.id, team_id=None, team_role=None)


# ===========================================================================
# RBAC inheritance: dept-head has MANAGER reach over teams in their dept.
# ===========================================================================


async def test_dept_head_can_assign_member_to_team_in_their_dept(
    service: InviteService,
    members_repo: AsyncMock,
    teams_repo: AsyncMock,
    departments_repo: AsyncMock,
) -> None:
    """Dept-head principal (not workspace OWNER/ADMIN) assigning a
    member to a team under THEIR department — succeeds without needing
    a workspace-admin role."""
    workspace = uuid4()
    head_principal = _principal(role=MemberRole.WORKSPACE_USER, workspace_id=workspace)
    head_dept = _dept(workspace, dept_id=uuid4(), head_id=head_principal.member_id)
    target_team = _team(workspace, department_id=head_dept.id)
    target = _member(workspace, name="Alice")

    # Two get_for_head lookups need to differ by member_id: the target
    # is not a head; the principal IS a head.
    async def get_for_head(member_id: UUID):
        if member_id == head_principal.member_id:
            return head_dept
        return None

    members_repo.get_by_id.return_value = target
    teams_repo.get_by_id.return_value = target_team
    departments_repo.get_for_head.side_effect = get_for_head
    members_repo.set_team.side_effect = lambda _id, **kw: target

    await service.set_member_team(
        target.id,
        SetMemberTeamRequest(team_id=target_team.id, team_role=TeamRole.MEMBER),
        head_principal,
    )
    members_repo.set_team.assert_awaited_once_with(
        target.id, team_id=target_team.id, team_role=TeamRole.MEMBER
    )


async def test_dept_head_cannot_assign_member_to_team_outside_their_dept(
    service: InviteService,
    members_repo: AsyncMock,
    teams_repo: AsyncMock,
    departments_repo: AsyncMock,
) -> None:
    """Dept-head reach stops at the department boundary — a team in a
    DIFFERENT department denies with ForbiddenError."""
    workspace = uuid4()
    head_principal = _principal(role=MemberRole.WORKSPACE_USER, workspace_id=workspace)
    head_dept = _dept(workspace, dept_id=uuid4(), head_id=head_principal.member_id)
    foreign_dept = _dept(workspace, dept_id=uuid4())
    foreign_team = _team(workspace, department_id=foreign_dept.id)
    target = _member(workspace, name="Alice")

    async def get_for_head(member_id: UUID):
        if member_id == head_principal.member_id:
            return head_dept
        return None

    members_repo.get_by_id.return_value = target
    teams_repo.get_by_id.return_value = foreign_team
    departments_repo.get_for_head.side_effect = get_for_head

    with pytest.raises(ForbiddenError):
        await service.set_member_team(
            target.id,
            SetMemberTeamRequest(team_id=foreign_team.id, team_role=TeamRole.MEMBER),
            head_principal,
        )
    members_repo.set_team.assert_not_called()


async def test_non_admin_non_head_principal_still_forbidden(
    service: InviteService,
    members_repo: AsyncMock,
    teams_repo: AsyncMock,
    departments_repo: AsyncMock,
) -> None:
    """A plain WORKSPACE_USER with no head_id of any department still
    can't assign team membership — the inheritance is gated on actually
    heading a department."""
    workspace = uuid4()
    p = _principal(role=MemberRole.WORKSPACE_USER, workspace_id=workspace)
    target = _member(workspace, name="Alice")
    team = _team(workspace)

    members_repo.get_by_id.return_value = target
    teams_repo.get_by_id.return_value = team
    departments_repo.get_for_head.return_value = None

    with pytest.raises(ForbiddenError):
        await service.set_member_team(
            target.id,
            SetMemberTeamRequest(team_id=team.id, team_role=TeamRole.MEMBER),
            p,
        )


# ---------- password reset: org-scope match honours dept-head ----------


async def test_dept_head_can_reset_password_for_member_in_their_dept(
    service: InviteService,
    members_repo: AsyncMock,
    teams_repo: AsyncMock,
    departments_repo: AsyncMock,
    users_repo: AsyncMock,
) -> None:
    """The Department Head is implicitly granted MANAGER reach over
    every team in their dept; the password-reset org-scope check honours
    that. The same admin-only RBAC otherwise stops at team / department
    co-location."""
    workspace = uuid4()
    head_principal = _principal(
        role=MemberRole.WORKSPACE_ADMIN,  # admin role so the outer admin gate passes
        workspace_id=workspace,
        priority=2,
    )
    head_dept = _dept(workspace, dept_id=uuid4(), head_id=head_principal.member_id)
    member_team = _team(workspace, department_id=head_dept.id)
    head_member = _member(
        workspace, member_id=head_principal.member_id, name="HeadOfEng", team_id=None
    )
    target = _member(
        workspace,
        name="Alice",
        team_id=member_team.id,
        team_role=TeamRole.MEMBER,
    )

    async def get_by_id(mid: UUID):
        if mid == head_principal.member_id:
            return head_member
        return target

    async def team_by_id(tid: UUID):
        return member_team

    async def get_for_head(mid: UUID):
        if mid == head_principal.member_id:
            return head_dept
        return None

    members_repo.get_by_id.side_effect = get_by_id
    teams_repo.get_by_id.side_effect = team_by_id
    departments_repo.get_for_head.side_effect = get_for_head

    await service.admin_set_member_password(target.id, "new-password-123", head_principal)

    users_repo.update_password.assert_awaited_once()
    args = users_repo.update_password.await_args
    assert args.args[0] == target.user_id


async def test_dept_head_cannot_reset_password_for_member_outside_dept(
    service: InviteService,
    members_repo: AsyncMock,
    teams_repo: AsyncMock,
    departments_repo: AsyncMock,
    users_repo: AsyncMock,
) -> None:
    workspace = uuid4()
    head_principal = _principal(
        role=MemberRole.WORKSPACE_ADMIN,
        workspace_id=workspace,
        priority=2,
    )
    head_dept = _dept(workspace, dept_id=uuid4(), head_id=head_principal.member_id)
    foreign_dept = _dept(workspace, dept_id=uuid4())
    foreign_team = _team(workspace, department_id=foreign_dept.id)
    head_member = _member(
        workspace, member_id=head_principal.member_id, name="HeadOfEng", team_id=None
    )
    target = _member(workspace, name="Alice", team_id=foreign_team.id, team_role=TeamRole.MEMBER)

    async def get_by_id(mid: UUID):
        if mid == head_principal.member_id:
            return head_member
        return target

    async def team_by_id(tid: UUID):
        return foreign_team

    async def get_for_head(mid: UUID):
        if mid == head_principal.member_id:
            return head_dept
        return None

    members_repo.get_by_id.side_effect = get_by_id
    teams_repo.get_by_id.side_effect = team_by_id
    departments_repo.get_for_head.side_effect = get_for_head

    with pytest.raises(ForbiddenError):
        await service.admin_set_member_password(target.id, "new-password-123", head_principal)
    users_repo.update_password.assert_not_called()


# The InvalidMemberTypeError export is referenced via the cross-tenant
# guard inside admin_set_member_password; we don't directly raise it
# in these tests but the import documents the path.
_ = InvalidMemberTypeError
