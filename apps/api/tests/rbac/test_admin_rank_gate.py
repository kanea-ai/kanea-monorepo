"""Negative-authorization tests for admin-mutating endpoints.

This module is the structural fix for the test-category gap that let
issues #46 (agent admin-gate missing on PATCH/DELETE) and #51 (admin-
power rank gate missing on four tenants paths) slip through. The wider
test suite asserts "the allowed actor succeeds" extensively; it
almost never asserts "the forbidden actor is rejected." That asymmetry
is the root cause. New gated paths should land a negative-authz test
here so the gap doesn't reopen.

Two rules under audit:

1. **Admin-only route gate** (#46): PATCH and DELETE on /api/v1/agents/{id}
   must reject any non-admin caller at the framework layer
   (``WorkspaceAdminDep``). A non-admin should never reach the
   service.

2. **Admin-power rank gate** (#51): for the four tenants member-
   mutation paths, an ADMIN may act on members whose priority is
   numerically ≥ their own (inclusive ≥ — equal-or-lower rank).
   WORKSPACE_OWNER bypasses the rule (top of the access tree).
   Anyone strictly higher rank than the actor is off-limits.

The four tenants paths:
- ``InviteService.update_member_profile``
- ``InviteService.set_member_suspension``
- ``InviteService.set_member_team``
- ``InviteService.admin_set_member_password``

Asymmetry note: this rule is INCLUSIVE ≥. The delegation rule in
``TaskService._enforce_hierarchy`` is STRICT >. Both are intentional
and must remain separate — see #51 for the rationale. Do not extract
a single shared helper across the two.

Route-gate scope finding: three of the four tenants routes use
``WorkspaceAdminDep`` and reject WORKSPACE_USER at the framework
layer. The fourth — PATCH /members/{id}/team — intentionally uses
``PrincipalDep`` because the route also admits dept-heads who are
not admins (the role discrimination happens at the service layer).
The non-admin-rejected test for ``set_member_team`` therefore runs
against the service rather than the route, and the test for the
agents route runs at the framework layer. This is documented in the
relevant tests themselves so a future tightening of either path
breaks the test deliberately.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import jwt
import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_agent_service
from app.application.agents.schemas import AgentResponse
from app.application.tasks.schemas import Principal
from app.application.tenants.schemas import (
    SetMemberSuspensionRequest,
    SetMemberTeamRequest,
    UpdateMemberProfileRequest,
)
from app.application.tenants.service import InviteService
from app.core.config import settings
from app.domain.entities import Member
from app.domain.enums import MemberRole, MemberType, TeamRole
from app.domain.exceptions import ForbiddenError

# ---------------------------------------------------------------------------
# Factories — kept local to mirror the pattern used by sibling tests
# (test_invite_service.py, test_suspension_service.py, etc.). Each
# accepts the two axes this module actually varies: role and priority.
# ---------------------------------------------------------------------------


def _principal(
    *,
    role: MemberRole,
    priority: int,
    workspace_id: UUID | None = None,
    member_id: UUID | None = None,
) -> Principal:
    """Build a principal at an explicit (role, priority) pair.

    Both axes are required to make rank-gate tests legible: the rank
    gate's behaviour depends on the numerical priority delta, never
    on role-implied defaults."""
    return Principal(
        member_id=member_id or uuid4(),
        workspace_id=workspace_id or uuid4(),
        type=MemberType.HUMAN,
        priority=priority,
        scope="human",
        role=role,
    )


def _member(
    *,
    workspace_id: UUID,
    priority: int,
    role: MemberRole = MemberRole.WORKSPACE_USER,
    member_id: UUID | None = None,
    team_id: UUID | None = None,
    user_id: UUID | None = None,
) -> Member:
    """A workspace member at an explicit priority. user_id defaults to
    a fresh uuid so the password-reset path's HUMAN-has-user_id
    invariant doesn't break."""
    now = datetime.now(UTC)
    return Member(
        id=member_id or uuid4(),
        workspace_id=workspace_id,
        team_id=team_id,
        type=MemberType.HUMAN,
        name="Target",
        email="target@example.com",
        priority=priority,
        role=role,
        user_id=user_id or uuid4(),
        created_at=now,
        updated_at=now,
    )


# ---------------------------------------------------------------------------
# Service / TestClient fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def members_repo() -> AsyncMock:
    repo = AsyncMock()
    # The team-assignment service consults a sitting MANAGER/LEAD; default
    # to "no sitting role" so the happy paths don't need to wire it.
    repo.get_for_team_role.return_value = None
    return repo


@pytest.fixture
def teams_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def users_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def auth_members() -> AsyncMock:
    repo = AsyncMock()
    # Default to single membership so the password-reset cross-workspace
    # guard doesn't trip.
    repo.list_for_user.return_value = [
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
def hasher() -> MagicMock:
    h = MagicMock()
    h.hash.side_effect = lambda raw: f"bcrypt${raw}"
    return h


@pytest.fixture
def service(
    members_repo: AsyncMock,
    teams_repo: AsyncMock,
    users_repo: AsyncMock,
    auth_members: AsyncMock,
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
        teams=teams_repo,
        users=users_repo,
    )


def _bearer(
    *,
    role: MemberRole,
    priority: int = 2,
    workspace_id: UUID | None = None,
) -> dict[str, str]:
    """Forge a workspace-scoped HUMAN JWT for route-level tests."""
    now = datetime.now(UTC)
    payload = {
        "iss": settings.jwt_issuer,
        "sub": str(uuid4()),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=1)).timestamp()),
        "workspace_id": str(workspace_id or uuid4()),
        "type": MemberType.HUMAN.value,
        "priority": priority,
        "role": role.value,
        "scope": "human",
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def agent_service() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def client(agent_service: AsyncMock) -> Iterator[TestClient]:
    from app.main import app

    app.dependency_overrides[get_agent_service] = lambda: agent_service
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _agent_response_stub(name: str = "renamed") -> AgentResponse:
    return AgentResponse(
        id=uuid4(),
        workspace_id=uuid4(),
        name=name,
        priority=5,
        model=None,
        created_at=datetime.now(UTC),
        last_seen_at=None,
        health_status="STALE",
    )


# ===========================================================================
# Section 1 — #46: PATCH/DELETE /agents/{id} require admin at the route
# ===========================================================================
#
# These four tests pin the framework-layer admin gate on the two agent
# routes. Before #46's fix, both routes used PrincipalDep and accepted
# any authenticated workspace member; the negative-side assertion (USER
# → 403) was simply absent. With WorkspaceAdminDep in place plus the
# service-layer role assertion that POST /agents already has, a USER
# never reaches the handler.


def test_patch_agent_rejects_workspace_user_role(
    client: TestClient,
    agent_service: AsyncMock,
) -> None:
    """The route's admin gate must reject USER role with 403 BEFORE
    the service is touched. Mirrors the existing POST /agents pattern
    (test_create_agent_requires_admin)."""
    response = client.patch(
        f"/api/v1/agents/{uuid4()}",
        json={"name": "x"},
        headers=_bearer(role=MemberRole.WORKSPACE_USER),
    )
    assert response.status_code == 403
    agent_service.update_agent.assert_not_called()


def test_patch_agent_allows_admin_role(
    client: TestClient,
    agent_service: AsyncMock,
) -> None:
    """Positive pair for the negative test above — ADMIN passes the
    gate and reaches the handler."""
    agent_service.update_agent.return_value = _agent_response_stub()
    response = client.patch(
        f"/api/v1/agents/{uuid4()}",
        json={"name": "renamed"},
        headers=_bearer(role=MemberRole.WORKSPACE_ADMIN),
    )
    assert response.status_code == 200
    assert response.json()["name"] == "renamed"


def test_delete_agent_rejects_workspace_user_role(
    client: TestClient,
    agent_service: AsyncMock,
) -> None:
    """The DELETE route's admin gate must reject USER role with 403
    BEFORE the service is touched."""
    response = client.delete(
        f"/api/v1/agents/{uuid4()}",
        headers=_bearer(role=MemberRole.WORKSPACE_USER),
    )
    assert response.status_code == 403
    agent_service.delete_agent.assert_not_called()


def test_delete_agent_allows_admin_role(
    client: TestClient,
    agent_service: AsyncMock,
) -> None:
    """Positive pair — ADMIN passes the gate and the route 204s."""
    agent_service.delete_agent.return_value = None
    response = client.delete(
        f"/api/v1/agents/{uuid4()}",
        headers=_bearer(role=MemberRole.WORKSPACE_ADMIN),
    )
    assert response.status_code == 204


# ===========================================================================
# Section 2 — #51: admin-power rank gate on four tenants paths
# ===========================================================================
#
# For each of update_member_profile / set_member_suspension /
# set_member_team / admin_set_member_password, five tests pin the
# contract:
#
# - rejects_non_admin_role     — WORKSPACE_USER → ForbiddenError
#                                (pins the existing role gate; route-
#                                level for 3 of 4, service-level for
#                                set_member_team — see module docstring)
# - rejects_admin_on_higher    — ADMIN(prio=4) on target(prio=1) → 403
# - allows_admin_on_equal      — ADMIN(prio=2) on target(prio=2) → ok
#                                (pins the INCLUSIVE ≥ semantic; an
#                                accidental strict > would break this)
# - allows_admin_on_lower      — ADMIN(prio=2) on target(prio=5) → ok
# - owner_bypass_on_higher     — OWNER(prio=5) on target(prio=1) → ok
#                                (priority is intentionally inverted vs
#                                role here: an OWNER with a stale-high
#                                priority must STILL bypass the rank
#                                check; the role check short-circuits)
#
# Existing happy-path tests live in their original homes
# (tests/tenants/, tests/suspension/); this module only adds the
# rank-axis cases that were missing.


# --------- update_member_profile ---------


async def test_update_member_profile_rejects_non_admin_role(
    service: InviteService,
    members_repo: AsyncMock,
) -> None:
    """Pin the existing route+service admin gate. WORKSPACE_USER
    cannot edit anyone's profile, regardless of target rank."""
    p = _principal(role=MemberRole.WORKSPACE_USER, priority=5)
    with pytest.raises(ForbiddenError):
        await service.update_member_profile(
            uuid4(),
            UpdateMemberProfileRequest(name="x"),
            p,
        )
    members_repo.update_profile.assert_not_called()


async def test_update_member_profile_rejects_admin_acting_on_higher_rank_admin(
    service: InviteService,
    members_repo: AsyncMock,
) -> None:
    """The rank-gate finding (#51). An ADMIN at priority 4 cannot
    rename / demote / re-priority a peer at priority 1."""
    p = _principal(role=MemberRole.WORKSPACE_ADMIN, priority=4)
    target = _member(
        workspace_id=p.workspace_id,
        priority=1,
        role=MemberRole.WORKSPACE_ADMIN,
    )
    members_repo.get_by_id.return_value = target

    with pytest.raises(ForbiddenError, match="higher rank"):
        await service.update_member_profile(
            target.id,
            UpdateMemberProfileRequest(name="Renamed"),
            p,
        )
    members_repo.update_profile.assert_not_called()


async def test_update_member_profile_allows_admin_acting_on_equal_rank_admin(
    service: InviteService,
    members_repo: AsyncMock,
) -> None:
    """Pin the INCLUSIVE ≥ semantic. Two priority-2 admins can act
    on each other — equal-rank mutual action is intentional under #51
    (the workspace owner is the backstop)."""
    p = _principal(role=MemberRole.WORKSPACE_ADMIN, priority=2)
    target = _member(
        workspace_id=p.workspace_id,
        priority=2,
        role=MemberRole.WORKSPACE_ADMIN,
    )
    members_repo.get_by_id.return_value = target
    members_repo.update_profile.return_value = target

    await service.update_member_profile(
        target.id,
        UpdateMemberProfileRequest(name="Renamed"),
        p,
    )
    members_repo.update_profile.assert_awaited_once()


async def test_update_member_profile_allows_admin_acting_on_lower_rank_member(
    service: InviteService,
    members_repo: AsyncMock,
) -> None:
    """The everyday case: ADMIN(prio=2) renames USER(prio=5)."""
    p = _principal(role=MemberRole.WORKSPACE_ADMIN, priority=2)
    target = _member(workspace_id=p.workspace_id, priority=5)
    members_repo.get_by_id.return_value = target
    members_repo.update_profile.return_value = target

    await service.update_member_profile(
        target.id,
        UpdateMemberProfileRequest(name="Renamed"),
        p,
    )
    members_repo.update_profile.assert_awaited_once()


async def test_update_member_profile_owner_bypass_on_higher_rank_target(
    service: InviteService,
    members_repo: AsyncMock,
) -> None:
    """Owner bypass short-circuits the rank check. Intentionally use
    a stale-high priority on the OWNER (prio=5) acting on a target at
    prio=1: a non-owner ADMIN would be rejected here, but the OWNER
    passes purely on role."""
    p = _principal(role=MemberRole.WORKSPACE_OWNER, priority=5)
    target = _member(
        workspace_id=p.workspace_id,
        priority=1,
        role=MemberRole.WORKSPACE_ADMIN,
    )
    members_repo.get_by_id.return_value = target
    members_repo.update_profile.return_value = target

    await service.update_member_profile(
        target.id,
        UpdateMemberProfileRequest(name="Renamed"),
        p,
    )
    members_repo.update_profile.assert_awaited_once()


# --------- set_member_suspension ---------


async def test_set_member_suspension_rejects_non_admin_role(
    service: InviteService,
    members_repo: AsyncMock,
) -> None:
    """Pin the existing role gate on the suspension path."""
    p = _principal(role=MemberRole.WORKSPACE_USER, priority=5)
    with pytest.raises(ForbiddenError):
        await service.set_member_suspension(
            uuid4(),
            SetMemberSuspensionRequest(is_suspended=True),
            p,
        )
    members_repo.set_suspended.assert_not_called()


async def test_set_member_suspension_rejects_admin_acting_on_higher_rank_admin(
    service: InviteService,
    members_repo: AsyncMock,
) -> None:
    p = _principal(role=MemberRole.WORKSPACE_ADMIN, priority=4)
    target = _member(
        workspace_id=p.workspace_id,
        priority=1,
        role=MemberRole.WORKSPACE_ADMIN,
    )
    members_repo.get_by_id.return_value = target

    with pytest.raises(ForbiddenError, match="higher rank"):
        await service.set_member_suspension(
            target.id,
            SetMemberSuspensionRequest(is_suspended=True),
            p,
        )
    members_repo.set_suspended.assert_not_called()


async def test_set_member_suspension_allows_admin_acting_on_equal_rank_admin(
    service: InviteService,
    members_repo: AsyncMock,
) -> None:
    p = _principal(role=MemberRole.WORKSPACE_ADMIN, priority=2)
    target = _member(
        workspace_id=p.workspace_id,
        priority=2,
        role=MemberRole.WORKSPACE_ADMIN,
    )
    members_repo.get_by_id.return_value = target
    members_repo.set_suspended.return_value = target

    await service.set_member_suspension(
        target.id,
        SetMemberSuspensionRequest(is_suspended=True),
        p,
    )
    members_repo.set_suspended.assert_awaited_once()


async def test_set_member_suspension_allows_admin_acting_on_lower_rank_member(
    service: InviteService,
    members_repo: AsyncMock,
) -> None:
    p = _principal(role=MemberRole.WORKSPACE_ADMIN, priority=2)
    target = _member(workspace_id=p.workspace_id, priority=5)
    members_repo.get_by_id.return_value = target
    members_repo.set_suspended.return_value = target

    await service.set_member_suspension(
        target.id,
        SetMemberSuspensionRequest(is_suspended=True),
        p,
    )
    members_repo.set_suspended.assert_awaited_once()


async def test_set_member_suspension_owner_bypass_on_higher_rank_target(
    service: InviteService,
    members_repo: AsyncMock,
) -> None:
    """OWNER(prio=5) acts on ADMIN(prio=1). Last-active-owner guard
    is not in play here (target isn't OWNER), so the bypass alone
    determines the outcome."""
    p = _principal(role=MemberRole.WORKSPACE_OWNER, priority=5)
    target = _member(
        workspace_id=p.workspace_id,
        priority=1,
        role=MemberRole.WORKSPACE_ADMIN,
    )
    members_repo.get_by_id.return_value = target
    members_repo.set_suspended.return_value = target

    await service.set_member_suspension(
        target.id,
        SetMemberSuspensionRequest(is_suspended=True),
        p,
    )
    members_repo.set_suspended.assert_awaited_once()


# --------- set_member_team ---------


async def test_set_member_team_rejects_non_admin_role_at_service_level(
    service: InviteService,
    members_repo: AsyncMock,
) -> None:
    """The PATCH /members/{id}/team route intentionally uses
    PrincipalDep, not WorkspaceAdminDep, because the route also
    admits dept-heads (who are not workspace admins). Role
    discrimination therefore happens at the SERVICE layer. This test
    pins the service-level rejection for a plain WORKSPACE_USER who
    is also not a dept-head — if a future refactor moves the role
    check elsewhere, this fails deliberately.

    The route-level pin is intentionally absent: tightening the route
    to WorkspaceAdminDep would lock out dept-heads, which is a
    separate product question not in scope for #51."""
    p = _principal(role=MemberRole.WORKSPACE_USER, priority=5)
    with pytest.raises(ForbiddenError):
        await service.set_member_team(
            uuid4(),
            SetMemberTeamRequest(team_id=uuid4(), team_role=TeamRole.MEMBER),
            p,
        )
    members_repo.set_team.assert_not_called()


async def test_set_member_team_rejects_admin_acting_on_higher_rank_admin(
    service: InviteService,
    members_repo: AsyncMock,
    teams_repo: AsyncMock,
) -> None:
    p = _principal(role=MemberRole.WORKSPACE_ADMIN, priority=4)
    target = _member(
        workspace_id=p.workspace_id,
        priority=1,
        role=MemberRole.WORKSPACE_ADMIN,
    )
    team_id = uuid4()
    members_repo.get_by_id.return_value = target
    # Side-effect set so that if the rank gate is missing (the RED
    # condition) the service runs through to set_team(); the test
    # then fails cleanly at "DID NOT RAISE" rather than at Pydantic
    # response-construction on an AsyncMock return value.
    members_repo.set_team.side_effect = lambda _id, **kw: target
    from datetime import UTC, datetime

    from app.domain.entities import Team

    teams_repo.get_by_id.return_value = Team(
        id=team_id,
        workspace_id=p.workspace_id,
        name="Backend",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    with pytest.raises(ForbiddenError, match="higher rank"):
        await service.set_member_team(
            target.id,
            SetMemberTeamRequest(team_id=team_id, team_role=TeamRole.MEMBER),
            p,
        )
    members_repo.set_team.assert_not_called()


async def test_set_member_team_allows_admin_acting_on_equal_rank_admin(
    service: InviteService,
    members_repo: AsyncMock,
    teams_repo: AsyncMock,
) -> None:
    p = _principal(role=MemberRole.WORKSPACE_ADMIN, priority=2)
    target = _member(
        workspace_id=p.workspace_id,
        priority=2,
        role=MemberRole.WORKSPACE_ADMIN,
    )
    team_id = uuid4()
    members_repo.get_by_id.return_value = target
    members_repo.set_team.side_effect = lambda _id, **kw: target
    from datetime import UTC, datetime

    from app.domain.entities import Team

    teams_repo.get_by_id.return_value = Team(
        id=team_id,
        workspace_id=p.workspace_id,
        name="Backend",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    await service.set_member_team(
        target.id,
        SetMemberTeamRequest(team_id=team_id, team_role=TeamRole.MEMBER),
        p,
    )
    members_repo.set_team.assert_awaited_once()


async def test_set_member_team_allows_admin_acting_on_lower_rank_member(
    service: InviteService,
    members_repo: AsyncMock,
    teams_repo: AsyncMock,
) -> None:
    p = _principal(role=MemberRole.WORKSPACE_ADMIN, priority=2)
    target = _member(workspace_id=p.workspace_id, priority=5)
    team_id = uuid4()
    members_repo.get_by_id.return_value = target
    members_repo.set_team.side_effect = lambda _id, **kw: target
    from datetime import UTC, datetime

    from app.domain.entities import Team

    teams_repo.get_by_id.return_value = Team(
        id=team_id,
        workspace_id=p.workspace_id,
        name="Backend",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    await service.set_member_team(
        target.id,
        SetMemberTeamRequest(team_id=team_id, team_role=TeamRole.MEMBER),
        p,
    )
    members_repo.set_team.assert_awaited_once()


async def test_set_member_team_owner_bypass_on_higher_rank_target(
    service: InviteService,
    members_repo: AsyncMock,
    teams_repo: AsyncMock,
) -> None:
    p = _principal(role=MemberRole.WORKSPACE_OWNER, priority=5)
    target = _member(
        workspace_id=p.workspace_id,
        priority=1,
        role=MemberRole.WORKSPACE_ADMIN,
    )
    team_id = uuid4()
    members_repo.get_by_id.return_value = target
    members_repo.set_team.side_effect = lambda _id, **kw: target
    from datetime import UTC, datetime

    from app.domain.entities import Team

    teams_repo.get_by_id.return_value = Team(
        id=team_id,
        workspace_id=p.workspace_id,
        name="Backend",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    await service.set_member_team(
        target.id,
        SetMemberTeamRequest(team_id=team_id, team_role=TeamRole.MEMBER),
        p,
    )
    members_repo.set_team.assert_awaited_once()


# --------- admin_set_member_password ---------


async def test_admin_set_member_password_rejects_non_admin_role(
    service: InviteService,
    members_repo: AsyncMock,
    users_repo: AsyncMock,
) -> None:
    """Pin the existing role gate on the password-reset path."""
    p = _principal(role=MemberRole.WORKSPACE_USER, priority=5)
    with pytest.raises(ForbiddenError):
        await service.admin_set_member_password(uuid4(), "supersecret123", p)
    users_repo.update_password.assert_not_called()


async def test_admin_set_member_password_rejects_admin_acting_on_higher_rank_admin(
    service: InviteService,
    members_repo: AsyncMock,
    users_repo: AsyncMock,
) -> None:
    """Today the route blocks ADMIN→OWNER via the role check in
    _require_org_scope_match, but ADMIN→higher-rank-ADMIN slips
    through. The rank gate closes this."""
    p = _principal(role=MemberRole.WORKSPACE_ADMIN, priority=4)
    team_id = uuid4()
    target = _member(
        workspace_id=p.workspace_id,
        priority=1,
        role=MemberRole.WORKSPACE_ADMIN,
        team_id=team_id,
    )
    # Same team as the admin so the org-scope check doesn't fire
    # first (we want the rank gate to be the load-bearing rejection).
    admin_self = _member(
        workspace_id=p.workspace_id,
        member_id=p.member_id,
        priority=4,
        role=MemberRole.WORKSPACE_ADMIN,
        team_id=team_id,
    )
    members_repo.get_by_id.side_effect = lambda mid: (
        target if mid == target.id else admin_self if mid == p.member_id else None
    )

    with pytest.raises(ForbiddenError, match="higher rank"):
        await service.admin_set_member_password(target.id, "supersecret123", p)
    users_repo.update_password.assert_not_called()


async def test_admin_set_member_password_allows_admin_acting_on_equal_rank_admin(
    service: InviteService,
    members_repo: AsyncMock,
    users_repo: AsyncMock,
) -> None:
    p = _principal(role=MemberRole.WORKSPACE_ADMIN, priority=2)
    team_id = uuid4()
    target = _member(
        workspace_id=p.workspace_id,
        priority=2,
        role=MemberRole.WORKSPACE_ADMIN,
        team_id=team_id,
    )
    admin_self = _member(
        workspace_id=p.workspace_id,
        member_id=p.member_id,
        priority=2,
        role=MemberRole.WORKSPACE_ADMIN,
        team_id=team_id,
    )
    members_repo.get_by_id.side_effect = lambda mid: (
        target if mid == target.id else admin_self if mid == p.member_id else None
    )

    await service.admin_set_member_password(target.id, "supersecret123", p)
    users_repo.update_password.assert_awaited_once()


async def test_admin_set_member_password_allows_admin_acting_on_lower_rank_member(
    service: InviteService,
    members_repo: AsyncMock,
    users_repo: AsyncMock,
) -> None:
    p = _principal(role=MemberRole.WORKSPACE_ADMIN, priority=2)
    team_id = uuid4()
    target = _member(workspace_id=p.workspace_id, priority=5, team_id=team_id)
    admin_self = _member(
        workspace_id=p.workspace_id,
        member_id=p.member_id,
        priority=2,
        role=MemberRole.WORKSPACE_ADMIN,
        team_id=team_id,
    )
    members_repo.get_by_id.side_effect = lambda mid: (
        target if mid == target.id else admin_self if mid == p.member_id else None
    )

    await service.admin_set_member_password(target.id, "supersecret123", p)
    users_repo.update_password.assert_awaited_once()


async def test_admin_set_member_password_owner_bypass_on_higher_rank_target(
    service: InviteService,
    members_repo: AsyncMock,
    users_repo: AsyncMock,
) -> None:
    """OWNER(prio=5) resets ADMIN(prio=1). Org-scope check is skipped
    for OWNERs (existing behaviour), so this exercises the rank-gate
    bypass cleanly."""
    p = _principal(role=MemberRole.WORKSPACE_OWNER, priority=5)
    target = _member(
        workspace_id=p.workspace_id,
        priority=1,
        role=MemberRole.WORKSPACE_ADMIN,
    )
    members_repo.get_by_id.return_value = target

    await service.admin_set_member_password(target.id, "supersecret123", p)
    users_repo.update_password.assert_awaited_once()
