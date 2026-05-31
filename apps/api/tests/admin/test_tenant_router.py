"""Workspace drill-down + tenant intervention surface.

Three endpoints, all gated by ``SuperadminDep``:

* ``GET /api/v1/admin/workspaces/{id}`` — granular workspace stats.
* ``GET /api/v1/admin/workspaces/{id}/users`` — paginated user list
  with the hierarchy slot (team + team_role + headed dept).
* ``PATCH /api/v1/admin/workspaces/{id}/users/{user_id}`` —
  superadmin intervention. The orchestrator routes writes through
  DepartmentService + InviteService so every Round-2 constraint
  (head clears team, one MANAGER per team, auto-demote-and-promote)
  carries over verbatim.

The service-level tests below assert that the orchestrator wires the
existing services in the right order rather than re-implementing the
constraint logic.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import jwt
import pytest
from fastapi.testclient import TestClient

from app.api.deps import (
    get_admin_tenant_service,
    get_member_repository,
    get_user_repository,
)
from app.application.admin.tenant_ports import (
    WorkspaceDetailRow,
    WorkspaceStatusCounts,
    WorkspaceUserDetailRow,
)
from app.application.admin.tenant_schemas import (
    AdminAgentRow,
    AdminMemberStats,
    AdminWorkspaceDetail,
    AdminWorkspaceUserRow,
    PatchWorkspaceMemberRequest,
    PatchWorkspaceUserRequest,
    WorkspaceStatusBreakdown,
)
from app.application.admin.tenant_service import (
    AdminTenantService,
    WorkspaceUserDualScopeError,
)
from app.application.pagination import Page
from app.core.config import settings
from app.domain.entities import Member, User, Workspace
from app.domain.enums import MemberRole, MemberType, TeamRole
from app.main import app


def _bearer(*, member_id: UUID, workspace_id: UUID) -> dict[str, str]:
    now = datetime.now(UTC)
    payload = {
        "iss": settings.jwt_issuer,
        "sub": str(member_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=1)).timestamp()),
        "workspace_id": str(workspace_id),
        "type": "HUMAN",
        "priority": 1,
        "role": MemberRole.WORKSPACE_OWNER.value,
        "scope": "human",
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return {"Authorization": f"Bearer {token}"}


def _member(*, member_id, workspace_id, user_id) -> Member:
    return Member(
        id=member_id,
        workspace_id=workspace_id,
        type=MemberType.HUMAN,
        name="Root",
        priority=1,
        role=MemberRole.WORKSPACE_OWNER,
        user_id=user_id,
    )


def _user(user_id: UUID, *, is_superadmin: bool = True) -> User:
    return User(
        id=user_id,
        email="root@kanea.ai",
        full_name="Root",
        password_hash="h",
        is_superadmin=is_superadmin,
    )


def _workspace_detail_row(name="Acme", slug="acme") -> tuple[Workspace, AdminWorkspaceDetail]:
    """Helper that builds a Workspace + matching AdminWorkspaceDetail
    response for the GET /workspaces/{id} case."""
    now = datetime.now(UTC)
    ws = Workspace(
        id=uuid4(),
        name=name,
        slug=slug,
        task_prefix=slug.upper()[:8],
        next_task_seq=1,
        created_at=now,
        updated_at=now,
    )
    detail = AdminWorkspaceDetail(
        id=ws.id,
        name=ws.name,
        slug=ws.slug,
        task_prefix=ws.task_prefix,
        suspended_at=None,
        created_at=now,
        updated_at=now,
        total_users=12,
        total_tasks=345,
        total_tokens_used=67_890,
        total_teams=4,
        total_departments=2,
        total_projects=5,
        status_breakdown=WorkspaceStatusBreakdown(
            pending=10, in_progress=5, in_review=3, done=320, cancelled=7, blocked=2
        ),
    )
    return ws, detail


# ---------- fixtures ----------


@pytest.fixture
def tenant_service() -> AsyncMock:
    return AsyncMock(spec=AdminTenantService)


@pytest.fixture
def members_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def users_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def principal_ids() -> tuple[UUID, UUID, UUID]:
    return uuid4(), uuid4(), uuid4()


@pytest.fixture
def client(
    tenant_service: AsyncMock,
    members_repo: AsyncMock,
    users_repo: AsyncMock,
    principal_ids: tuple[UUID, UUID, UUID],
) -> Iterator[TestClient]:
    member_id, workspace_id, user_id = principal_ids
    members_repo.get_by_id.return_value = _member(
        member_id=member_id, workspace_id=workspace_id, user_id=user_id
    )
    users_repo.get_by_id.return_value = _user(user_id, is_superadmin=True)
    app.dependency_overrides[get_member_repository] = lambda: members_repo
    app.dependency_overrides[get_user_repository] = lambda: users_repo
    app.dependency_overrides[get_admin_tenant_service] = lambda: tenant_service
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_member_repository, None)
        app.dependency_overrides.pop(get_user_repository, None)
        app.dependency_overrides.pop(get_admin_tenant_service, None)


@pytest.fixture
def auth_headers(principal_ids: tuple[UUID, UUID, UUID]) -> dict[str, str]:
    member_id, workspace_id, _ = principal_ids
    return _bearer(member_id=member_id, workspace_id=workspace_id)


# ---------- workspace detail ----------


def test_workspace_detail_returns_stats_grid(
    client: TestClient, tenant_service: AsyncMock, auth_headers: dict[str, str]
) -> None:
    _, detail = _workspace_detail_row()
    tenant_service.get_workspace_detail.return_value = detail
    response = client.get(f"/api/v1/admin/workspaces/{detail.id}", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["slug"] == "acme"
    assert body["total_users"] == 12
    assert body["status_breakdown"]["done"] == 320
    assert body["status_breakdown"]["blocked"] == 2


# ---------- workspace users ----------


def test_workspace_users_returns_hierarchy_slot(
    client: TestClient, tenant_service: AsyncMock, auth_headers: dict[str, str]
) -> None:
    row = AdminWorkspaceUserRow(
        member_id=uuid4(),
        user_id=uuid4(),
        email="alice@acme.io",
        full_name="Alice",
        type=MemberType.HUMAN,
        role=MemberRole.WORKSPACE_USER,
        is_suspended=False,
        team_id=uuid4(),
        team_name="Backend",
        team_role=TeamRole.MANAGER,
        team_department_id=uuid4(),
        team_department_name="Engineering",
        headed_department_id=None,
        headed_department_name=None,
    )
    tenant_service.list_workspace_users.return_value = Page[AdminWorkspaceUserRow](
        items=[row], total=1
    )
    response = client.get(
        f"/api/v1/admin/workspaces/{uuid4()}/users?skip=0&limit=10",
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["team_role"] == "MANAGER"
    assert body["items"][0]["team_department_name"] == "Engineering"


def test_workspace_users_serialises_agent_with_null_user_id(
    client: TestClient, tenant_service: AsyncMock, auth_headers: dict[str, str]
) -> None:
    # Agents have no backing user row (CHECK on members: AGENT ⇒ user_id NULL).
    # If the response schema treats user_id as non-nullable, the listing 500s
    # on any workspace that contains an agent — which was the actual prod bug.
    agent_row = AdminWorkspaceUserRow(
        member_id=uuid4(),
        user_id=None,
        email=None,
        full_name="Aria (Agent)",
        type=MemberType.AGENT,
        role=MemberRole.WORKSPACE_USER,
        is_suspended=False,
        team_id=None,
        team_name=None,
        team_role=None,
        team_department_id=None,
        team_department_name=None,
        headed_department_id=None,
        headed_department_name=None,
    )
    tenant_service.list_workspace_users.return_value = Page[AdminWorkspaceUserRow](
        items=[agent_row], total=1
    )
    response = client.get(
        f"/api/v1/admin/workspaces/{uuid4()}/users",
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["user_id"] is None
    assert body["items"][0]["type"] == "AGENT"


# ---------- patch ----------


def test_patch_user_dual_scope_is_400(
    client: TestClient, tenant_service: AsyncMock, auth_headers: dict[str, str]
) -> None:
    tenant_service.patch_workspace_user.side_effect = WorkspaceUserDualScopeError(
        "a user cannot simultaneously be a Department Head and on a Team"
    )
    response = client.patch(
        f"/api/v1/admin/workspaces/{uuid4()}/users/{uuid4()}",
        json={"team_id": str(uuid4()), "department_id": str(uuid4())},
        headers=auth_headers,
    )
    assert response.status_code == 400


def test_patch_user_routes_through_service(
    client: TestClient, tenant_service: AsyncMock, auth_headers: dict[str, str]
) -> None:
    """Just confirms the route maps body -> service.patch_workspace_user.
    Service-level behaviour (orchestration) is covered below."""
    ws_id = uuid4()
    target_user_id = uuid4()
    new_team_id = uuid4()
    tenant_service.patch_workspace_user.return_value = AdminWorkspaceUserRow(
        member_id=uuid4(),
        user_id=target_user_id,
        email=None,
        full_name="x",
        type=MemberType.HUMAN,
        role=MemberRole.WORKSPACE_USER,
        is_suspended=False,
        team_id=new_team_id,
        team_name="t",
        team_role=TeamRole.MEMBER,
        team_department_id=None,
        team_department_name=None,
        headed_department_id=None,
        headed_department_name=None,
    )
    response = client.patch(
        f"/api/v1/admin/workspaces/{ws_id}/users/{target_user_id}",
        json={"team_id": str(new_team_id), "team_role": "MEMBER"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    args = tenant_service.patch_workspace_user.await_args
    assert args.args[0] == ws_id
    assert args.args[1] == target_user_id


def test_patch_workspace_not_found_404s(
    client: TestClient, tenant_service: AsyncMock, auth_headers: dict[str, str]
) -> None:
    from app.domain.exceptions import WorkspaceNotFoundError

    tenant_service.patch_workspace_user.side_effect = WorkspaceNotFoundError("workspace not found")
    response = client.patch(
        f"/api/v1/admin/workspaces/{uuid4()}/users/{uuid4()}",
        json={"team_id": str(uuid4()), "team_role": "MEMBER"},
        headers=auth_headers,
    )
    assert response.status_code == 404


# ---------- service-level orchestration ----------


def _user_row(*, team_id=None, headed_dept_id=None, member_id=None, user_id=None):
    return WorkspaceUserDetailRow(
        member_id=member_id or uuid4(),
        user_id=user_id or uuid4(),
        email="alice@acme.io",
        full_name="Alice",
        type=MemberType.HUMAN,
        role=MemberRole.WORKSPACE_USER,
        is_suspended=False,
        team_id=team_id,
        team_name=None if team_id is None else "Backend",
        team_role=None if team_id is None else TeamRole.MEMBER,
        team_department_id=None,
        team_department_name=None,
        headed_department_id=headed_dept_id,
        headed_department_name=None if headed_dept_id is None else "Engineering",
    )


@pytest.fixture
def workspaces_repo_for_service() -> AsyncMock:
    r = AsyncMock()
    # Always return a workspace so the existence check passes.
    now = datetime.now(UTC)
    r.get_by_id.return_value = Workspace(
        id=uuid4(),
        name="Acme",
        slug="acme",
        task_prefix="ACME",
        next_task_seq=1,
        created_at=now,
        updated_at=now,
    )
    return r


@pytest.fixture
def tenant_repo_for_service() -> AsyncMock:
    r = AsyncMock()
    r.find_first_owner_member_id.return_value = uuid4()
    return r


@pytest.fixture
def departments_service() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def invites_service() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(
    workspaces_repo_for_service: AsyncMock,
    tenant_repo_for_service: AsyncMock,
    departments_service: AsyncMock,
    invites_service: AsyncMock,
) -> AdminTenantService:
    return AdminTenantService(
        tenant=tenant_repo_for_service,
        workspaces=workspaces_repo_for_service,
        departments=departments_service,
        invites=invites_service,
    )


async def test_service_patch_promotes_to_head_via_departments_service(
    service: AdminTenantService,
    tenant_repo_for_service: AsyncMock,
    departments_service: AsyncMock,
    invites_service: AsyncMock,
) -> None:
    """``department_id`` set → orchestrator calls DepartmentService.update
    with ``head_id`` = the member's id. The Round-2 isolation rule (clear
    team) lives inside DepartmentService so we just assert the call."""
    target_user_id = uuid4()
    new_dept_id = uuid4()
    existing = _user_row(user_id=target_user_id)
    refreshed = _user_row(user_id=target_user_id, headed_dept_id=new_dept_id)
    tenant_repo_for_service.find_member_by_user.side_effect = [existing, refreshed]
    await service.patch_workspace_user(
        uuid4(),
        target_user_id,
        PatchWorkspaceUserRequest(department_id=new_dept_id),
        superadmin_user_id=uuid4(),
    )
    departments_service.update.assert_awaited_once()
    args = departments_service.update.await_args
    assert args.args[0] == new_dept_id
    assert args.args[1].head_id == existing.member_id
    invites_service.set_member_team.assert_not_called()


async def test_service_patch_demotes_when_setting_team_on_current_head(
    service: AdminTenantService,
    tenant_repo_for_service: AsyncMock,
    departments_service: AsyncMock,
    invites_service: AsyncMock,
) -> None:
    """Spec carve-out: a superadmin assigning a Team to a sitting
    Department Head transparently demotes them from headship first,
    then runs the team assignment through InviteService."""
    target_user_id = uuid4()
    headed_dept_id = uuid4()
    new_team_id = uuid4()
    existing = _user_row(user_id=target_user_id, headed_dept_id=headed_dept_id)
    refreshed = _user_row(user_id=target_user_id, team_id=new_team_id)
    tenant_repo_for_service.find_member_by_user.side_effect = [existing, refreshed]
    await service.patch_workspace_user(
        uuid4(),
        target_user_id,
        PatchWorkspaceUserRequest(team_id=new_team_id, team_role=TeamRole.MEMBER),
        superadmin_user_id=uuid4(),
    )
    # The demotion comes first…
    departments_service.update.assert_awaited_once()
    args = departments_service.update.await_args
    assert args.args[0] == headed_dept_id
    # …with head_id explicitly cleared.
    assert args.args[1].head_id is None
    # …then the team assignment.
    invites_service.set_member_team.assert_awaited_once()


async def test_service_patch_rejects_dual_scope(
    service: AdminTenantService,
    tenant_repo_for_service: AsyncMock,
) -> None:
    with pytest.raises(WorkspaceUserDualScopeError):
        await service.patch_workspace_user(
            uuid4(),
            uuid4(),
            PatchWorkspaceUserRequest(team_id=uuid4(), department_id=uuid4()),
            superadmin_user_id=uuid4(),
        )


async def test_service_patch_department_null_demotes_head(
    service: AdminTenantService,
    tenant_repo_for_service: AsyncMock,
    departments_service: AsyncMock,
) -> None:
    """Explicit ``department_id = null`` removes the user from any
    department they head."""
    target_user_id = uuid4()
    headed_dept_id = uuid4()
    existing = _user_row(user_id=target_user_id, headed_dept_id=headed_dept_id)
    refreshed = _user_row(user_id=target_user_id)
    tenant_repo_for_service.find_member_by_user.side_effect = [existing, refreshed]
    await service.patch_workspace_user(
        uuid4(),
        target_user_id,
        PatchWorkspaceUserRequest.model_validate({"department_id": None}),
        superadmin_user_id=uuid4(),
    )
    departments_service.update.assert_awaited_once()
    args = departments_service.update.await_args
    assert args.args[0] == headed_dept_id
    assert args.args[1].head_id is None


# Keep these imports referenced so ruff doesn't strip them; exercised
# via the AsyncMock-spec'd service and the response objects above.
_ = WorkspaceDetailRow
_ = WorkspaceStatusCounts


# ---------- Task 3: member-id-keyed PATCH (humans + agents) ----------


def _agent_row(*, member_id=None, team_id=None):
    return WorkspaceUserDetailRow(
        member_id=member_id or uuid4(),
        user_id=None,
        email=None,
        full_name="Aria",
        type=MemberType.AGENT,
        role=MemberRole.WORKSPACE_USER,
        is_suspended=False,
        team_id=team_id,
        team_name=None if team_id is None else "Backend",
        team_role=None if team_id is None else TeamRole.MEMBER,
        team_department_id=None,
        team_department_name=None,
        headed_department_id=None,
        headed_department_name=None,
    )


def _row_to_response(row: WorkspaceUserDetailRow) -> AdminWorkspaceUserRow:
    return AdminWorkspaceUserRow.model_validate(row, from_attributes=True)


def test_patch_member_routes_through_service(
    client: TestClient, tenant_service: AsyncMock, auth_headers: dict[str, str]
) -> None:
    """New member-id-keyed endpoint forwards body + ids to the
    member-id service method. The user-id-keyed endpoint is unaffected."""
    ws_id = uuid4()
    target_member_id = uuid4()
    new_team_id = uuid4()
    tenant_service.patch_workspace_member.return_value = _row_to_response(
        _user_row(member_id=target_member_id, team_id=new_team_id)
    )
    response = client.patch(
        f"/api/v1/admin/workspaces/{ws_id}/members/{target_member_id}",
        json={"team_id": str(new_team_id), "team_role": "MEMBER"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    args = tenant_service.patch_workspace_member.await_args
    assert args.args[0] == ws_id
    assert args.args[1] == target_member_id


def test_patch_member_supports_agents(
    client: TestClient, tenant_service: AsyncMock, auth_headers: dict[str, str]
) -> None:
    """The whole point of the new endpoint: agents (user_id=NULL)
    must be editable. The response should round-trip with user_id null."""
    ws_id = uuid4()
    target_member_id = uuid4()
    new_team_id = uuid4()
    tenant_service.patch_workspace_member.return_value = _row_to_response(
        _agent_row(member_id=target_member_id, team_id=new_team_id)
    )
    response = client.patch(
        f"/api/v1/admin/workspaces/{ws_id}/members/{target_member_id}",
        json={"team_id": str(new_team_id), "team_role": "MEMBER"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] is None
    assert body["type"] == "AGENT"


def test_patch_member_dual_scope_is_400(
    client: TestClient, tenant_service: AsyncMock, auth_headers: dict[str, str]
) -> None:
    tenant_service.patch_workspace_member.side_effect = WorkspaceUserDualScopeError(
        "a user cannot simultaneously be a Department Head and on a Team"
    )
    response = client.patch(
        f"/api/v1/admin/workspaces/{uuid4()}/members/{uuid4()}",
        json={"team_id": str(uuid4()), "department_id": str(uuid4())},
        headers=auth_headers,
    )
    assert response.status_code == 400


def test_patch_member_accepts_workspace_role_and_priority(
    client: TestClient, tenant_service: AsyncMock, auth_headers: dict[str, str]
) -> None:
    """workspace_role + priority are new editable fields on the member-id
    endpoint. Verifies the route deserialises them and forwards them."""
    ws_id = uuid4()
    target_member_id = uuid4()
    tenant_service.patch_workspace_member.return_value = _row_to_response(
        _user_row(member_id=target_member_id)
    )
    response = client.patch(
        f"/api/v1/admin/workspaces/{ws_id}/members/{target_member_id}",
        json={"workspace_role": "WORKSPACE_ADMIN", "priority": 7},
        headers=auth_headers,
    )
    assert response.status_code == 200
    payload = tenant_service.patch_workspace_member.await_args.args[2]
    assert payload.workspace_role == MemberRole.WORKSPACE_ADMIN
    assert payload.priority == 7


def test_patch_member_forbids_unknown_fields(
    client: TestClient, tenant_service: AsyncMock, auth_headers: dict[str, str]
) -> None:
    """extra='forbid' on the schema — typos must 422 rather than silently no-op."""
    response = client.patch(
        f"/api/v1/admin/workspaces/{uuid4()}/members/{uuid4()}",
        json={"role": "WORKSPACE_ADMIN"},  # 'role' instead of 'workspace_role'
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_member_stats_routes_through_service(
    client: TestClient, tenant_service: AsyncMock, auth_headers: dict[str, str]
) -> None:
    ws_id = uuid4()
    member_id = uuid4()
    tenant_service.get_member_stats.return_value = AdminMemberStats(
        assigned_count=4,
        completed_count=11,
        avg_resolution_seconds=120.5,
        accuracy_percent=4.6,
        last_activity_at=datetime.now(UTC),
        total_tokens_used=2034,
    )
    response = client.get(
        f"/api/v1/admin/workspaces/{ws_id}/members/{member_id}/stats",
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["assigned_count"] == 4
    assert body["completed_count"] == 11


def test_member_stats_404_when_member_not_in_workspace(
    client: TestClient, tenant_service: AsyncMock, auth_headers: dict[str, str]
) -> None:
    from app.domain.exceptions import InvalidMemberTypeError

    tenant_service.get_member_stats.side_effect = InvalidMemberTypeError("member not found")
    response = client.get(
        f"/api/v1/admin/workspaces/{uuid4()}/members/{uuid4()}/stats",
        headers=auth_headers,
    )
    assert response.status_code == 404


# ---------- service-level: member-id orchestration ----------


async def test_service_patch_member_works_for_agent(
    service: AdminTenantService,
    tenant_repo_for_service: AsyncMock,
    invites_service: AsyncMock,
) -> None:
    """Agents have user_id=NULL; the orchestrator must route them
    through the member-id-keyed find/lookup path, not the user-id one."""
    target_member_id = uuid4()
    new_team_id = uuid4()
    existing = _agent_row(member_id=target_member_id)
    refreshed = _agent_row(member_id=target_member_id, team_id=new_team_id)
    tenant_repo_for_service.find_member_by_id.side_effect = [existing, refreshed]

    result = await service.patch_workspace_member(
        uuid4(),
        target_member_id,
        PatchWorkspaceMemberRequest(team_id=new_team_id, team_role=TeamRole.MEMBER),
        superadmin_user_id=uuid4(),
    )
    invites_service.set_member_team.assert_awaited_once()
    assert result.type == MemberType.AGENT
    assert result.user_id is None
    # find_member_by_user should NOT have been called for an agent path.
    tenant_repo_for_service.find_member_by_user.assert_not_called()


async def test_service_patch_member_routes_workspace_role_and_priority(
    service: AdminTenantService,
    tenant_repo_for_service: AsyncMock,
    invites_service: AsyncMock,
) -> None:
    """workspace_role + priority route through InviteService.update_member_profile
    so the last-OWNER guard and audit-logging stay intact."""
    target_member_id = uuid4()
    existing = _user_row(member_id=target_member_id)
    tenant_repo_for_service.find_member_by_id.side_effect = [existing, existing]
    await service.patch_workspace_member(
        uuid4(),
        target_member_id,
        PatchWorkspaceMemberRequest(
            workspace_role=MemberRole.WORKSPACE_ADMIN,
            priority=10,
        ),
        superadmin_user_id=uuid4(),
    )
    invites_service.update_member_profile.assert_awaited_once()
    args = invites_service.update_member_profile.await_args
    assert args.args[0] == target_member_id
    assert args.args[1].role == MemberRole.WORKSPACE_ADMIN
    assert args.args[1].priority == 10
    # No team / dept changes in this payload.
    invites_service.set_member_team.assert_not_called()


async def test_service_get_member_stats_delegates_to_repo(
    service: AdminTenantService,
    tenant_repo_for_service: AsyncMock,
) -> None:
    target_member_id = uuid4()
    existing = _user_row(member_id=target_member_id)
    tenant_repo_for_service.find_member_by_id.return_value = existing
    tenant_repo_for_service.compute_member_stats.return_value = AdminMemberStats(
        assigned_count=2,
        completed_count=5,
        avg_resolution_seconds=None,
        accuracy_percent=None,
        last_activity_at=None,
        total_tokens_used=99,
    )
    out = await service.get_member_stats(uuid4(), target_member_id)
    assert out.assigned_count == 2
    assert out.total_tokens_used == 99


async def test_service_get_member_stats_404s_when_member_missing(
    service: AdminTenantService,
    tenant_repo_for_service: AsyncMock,
) -> None:
    from app.domain.exceptions import InvalidMemberTypeError

    tenant_repo_for_service.find_member_by_id.return_value = None
    with pytest.raises(InvalidMemberTypeError):
        await service.get_member_stats(uuid4(), uuid4())


# ---------- Task 5: cross-tenant agents listing ----------


def test_list_agents_returns_paginated_rows(
    client: TestClient, tenant_service: AsyncMock, auth_headers: dict[str, str]
) -> None:
    """Cross-tenant agent grid for the unified /users surface — each
    row carries enough workspace context to open the detail panel
    directly without a follow-up lookup."""
    row = AdminAgentRow(
        member_id=uuid4(),
        workspace_id=uuid4(),
        workspace_name="Acme",
        workspace_slug="acme",
        full_name="Aria",
        created_at=datetime.now(UTC),
    )
    tenant_service.list_agents.return_value = Page[AdminAgentRow](items=[row], total=1)
    response = client.get("/api/v1/admin/agents?skip=0&limit=10", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["workspace_name"] == "Acme"
    assert body["items"][0]["full_name"] == "Aria"


def test_list_agents_supports_name_filter(
    client: TestClient, tenant_service: AsyncMock, auth_headers: dict[str, str]
) -> None:
    tenant_service.list_agents.return_value = Page[AdminAgentRow](items=[], total=0)
    response = client.get("/api/v1/admin/agents?name=ar", headers=auth_headers)
    assert response.status_code == 200
    args = tenant_service.list_agents.await_args
    # `name` is the only filter so far — kwargs are the easiest assertion.
    assert args.kwargs.get("name") == "ar"


# ---------- Task 5: single-member fetch by id ----------


def test_get_member_returns_row(
    client: TestClient, tenant_service: AsyncMock, auth_headers: dict[str, str]
) -> None:
    """Single-member detail endpoint — powers the unified panel when it
    needs to load a workspace-scoped slot for a row identified by
    workspace_id + member_id (e.g. an agent click from /users)."""
    ws_id = uuid4()
    member_id = uuid4()
    tenant_service.get_member.return_value = _row_to_response(_agent_row(member_id=member_id))
    response = client.get(
        f"/api/v1/admin/workspaces/{ws_id}/members/{member_id}",
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["member_id"] == str(member_id)
    assert body["type"] == "AGENT"


def test_get_member_404_when_not_in_workspace(
    client: TestClient, tenant_service: AsyncMock, auth_headers: dict[str, str]
) -> None:
    from app.domain.exceptions import InvalidMemberTypeError

    tenant_service.get_member.side_effect = InvalidMemberTypeError("member not found")
    response = client.get(
        f"/api/v1/admin/workspaces/{uuid4()}/members/{uuid4()}",
        headers=auth_headers,
    )
    assert response.status_code == 404
