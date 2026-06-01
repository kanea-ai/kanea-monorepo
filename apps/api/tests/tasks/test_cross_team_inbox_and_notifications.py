"""Track C — three plumbing bugs on top of the auto-fulfilling
cross-team request flow:

* Bug 1: GET /teams/{id}/requests filtered the wrong side of the
  relation. The corrected default returns INCOMING requests (filtered
  by requested_team_id); ?direction=outgoing keeps the old source-team
  view available.

* Bug 2: create_request emitted no notification at all. The corrected
  flow notifies the target team's leadership (MANAGER, LEAD, dept
  head), excluding the requester, with a workspace-owner fallback for
  leaderless teams so the request is never silently invisible.

* Bug 3: the auto-minted task carried no marker that it came from a
  cross-team request. TaskResponse.cross_team_origin is now populated
  for every list/detail flow; batched to a single SQL on list paths.

Issue #50 tracks the underlying lifecycle question (Model 2 approval
gate). These tests pin Model 1 (the current auto-fulfilment) behaviour.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from app.application.tasks.schemas import (
    CreateRequestPayload,
)
from app.application.tasks.service import TaskService
from app.domain.entities import Member, Notification, TaskRequest, Team
from app.domain.enums import (
    MemberRole,
    MemberType,
    NotificationType,
    RequestStatus,
    TeamRole,
)
from tests.tasks.factories import make_principal, make_task

# ---------- shared fixtures ----------


def _team(workspace_id, name="Target") -> Team:
    now = datetime.now(UTC)
    return Team(
        id=uuid4(),
        workspace_id=workspace_id,
        name=name,
        created_at=now,
        updated_at=now,
    )


def _member(
    *,
    workspace_id,
    member_id=None,
    user_id: UUID | None = None,
    team_id=None,
    team_role: TeamRole | None = None,
    role: MemberRole = MemberRole.WORKSPACE_USER,
    member_type: MemberType = MemberType.HUMAN,
    priority: int = 3,
) -> Member:
    return Member(
        id=member_id or uuid4(),
        workspace_id=workspace_id,
        type=member_type,
        name="member-x",
        email="x@example.com" if member_type is MemberType.HUMAN else None,
        priority=priority,
        role=role,
        team_id=team_id,
        team_role=team_role,
        # HUMAN members get a user_id (Notification.user_id is required);
        # AGENT members don't, by domain contract.
        user_id=(
            user_id
            if user_id is not None
            else (uuid4() if member_type is MemberType.HUMAN else None)
        ),
    )


@pytest.fixture
def task_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def members_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def relations_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def requests_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def teams_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def tenant_members_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def notifications_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def notifications_service(notifications_repo: AsyncMock) -> object:
    from app.application.notifications.service import NotificationService

    # Mention lookup not exercised by this file; AsyncMock is fine.
    return NotificationService(
        notifications=notifications_repo,
        members=AsyncMock(),
    )


@pytest.fixture
def service(
    task_repo: AsyncMock,
    members_repo: AsyncMock,
    workspace_repo: AsyncMock,
    seq_allocator: AsyncMock,
    teams_repo: AsyncMock,
    relations_repo: AsyncMock,
    requests_repo: AsyncMock,
    tenant_members_repo: AsyncMock,
    notifications_service: object,
) -> TaskService:
    return TaskService(
        tasks=task_repo,
        members=members_repo,
        workspaces=workspace_repo,
        seq_allocator=seq_allocator,
        team_lookup=teams_repo,
        relations=relations_repo,
        requests=requests_repo,
        notifications=notifications_service,
        tenant_members=tenant_members_repo,
    )


# ---------- Bug 1: inbox query direction ----------


async def test_inbox_default_direction_returns_incoming_requests(
    service: TaskService,
    requests_repo: AsyncMock,
    teams_repo: AsyncMock,
) -> None:
    """Default ``direction='incoming'`` calls the target-team repo
    method — the one filtering by ``requested_team_id``. The user-
    reported symptom (target team can't see incoming requests) is
    fixed by this routing change."""
    p = make_principal()
    target_team = _team(p.workspace_id)
    teams_repo.get_by_id.return_value = target_team
    requests_repo.list_for_target_team.return_value = []

    await service.list_requests_for_team_inbox(target_team.id, p)

    requests_repo.list_for_target_team.assert_awaited_once_with(target_team.id, status=None)
    requests_repo.list_for_source_team.assert_not_called()


async def test_inbox_outgoing_direction_returns_source_team_view(
    service: TaskService,
    requests_repo: AsyncMock,
    teams_repo: AsyncMock,
) -> None:
    """Explicit ``direction='outgoing'`` preserves the old behaviour —
    requests anchored to a source task LIVING on this team. Useful for
    a team that wants to see what they've asked for; not the default."""
    p = make_principal()
    own_team = _team(p.workspace_id)
    teams_repo.get_by_id.return_value = own_team
    requests_repo.list_for_source_team.return_value = []

    await service.list_requests_for_team_inbox(own_team.id, p, direction="outgoing")

    requests_repo.list_for_source_team.assert_awaited_once_with(own_team.id, status=None)
    requests_repo.list_for_target_team.assert_not_called()


async def test_inbox_status_filter_passes_through(
    service: TaskService,
    requests_repo: AsyncMock,
    teams_repo: AsyncMock,
) -> None:
    """A specific status filter is forwarded to the repo. The default
    (no filter) is what fixes the PENDING-trap — under auto-fulfilment
    new rows are born FULFILLED, so a default 'PENDING' filter would
    silently hide everything."""
    p = make_principal()
    team = _team(p.workspace_id)
    teams_repo.get_by_id.return_value = team
    requests_repo.list_for_target_team.return_value = []

    await service.list_requests_for_team_inbox(team.id, p, status_filter=RequestStatus.FULFILLED)

    requests_repo.list_for_target_team.assert_awaited_once_with(
        team.id, status=RequestStatus.FULFILLED
    )


# ---------- Bug 2: notifications on create_request ----------


async def _set_up_create_request(
    *,
    p,
    source_task,
    target_team,
    task_repo: AsyncMock,
    teams_repo: AsyncMock,
    relations_repo: AsyncMock,
    requests_repo: AsyncMock,
    seq_allocator: AsyncMock,
    members_repo: AsyncMock,
    target_task_id: UUID | None = None,
):
    """Helper that wires the minimum required mocks for a single
    create_request call to land. Each notification-recipient test
    overrides only the leadership lookups (tenant_members_repo)."""
    task_repo.get_by_id.return_value = source_task
    teams_repo.get_by_id.return_value = target_team
    teams_repo.get_department_head_for_team.return_value = None
    seq_allocator.allocate_next_task_seq.return_value = (101, "WS")
    task_repo.create.side_effect = lambda t: t
    relations_repo.create = AsyncMock()
    requests_repo.create.side_effect = lambda r: r
    # The fallback path requires workspace_prefix → mock workspaces.get_by_id.
    # (workspace_repo fixture is mocked at conftest level.)
    # Resolve assignee_name (for preview) returns "Alice".
    members_repo.get_by_id.return_value = Member(
        id=p.member_id,
        workspace_id=p.workspace_id,
        type=MemberType.HUMAN,
        name="Alice",
        email="alice@example.com",
        priority=p.priority,
        role=p.role,
        team_id=source_task.team_id,
        team_role=None,
        user_id=uuid4(),
    )


async def test_create_request_notifies_target_team_manager(
    service: TaskService,
    task_repo: AsyncMock,
    members_repo: AsyncMock,
    relations_repo: AsyncMock,
    requests_repo: AsyncMock,
    teams_repo: AsyncMock,
    tenant_members_repo: AsyncMock,
    notifications_repo: AsyncMock,
    seq_allocator: AsyncMock,
    workspace_repo: AsyncMock,
) -> None:
    p = make_principal(role=MemberRole.WORKSPACE_OWNER)
    source_task = make_task(workspace_id=p.workspace_id)
    target_team = _team(p.workspace_id)
    manager = _member(
        workspace_id=p.workspace_id,
        team_id=target_team.id,
        team_role=TeamRole.MANAGER,
    )
    tenant_members_repo.get_for_team_role.side_effect = lambda team_id, role: (
        manager if role is TeamRole.MANAGER else None
    )

    await _set_up_create_request(
        p=p,
        source_task=source_task,
        target_team=target_team,
        task_repo=task_repo,
        teams_repo=teams_repo,
        relations_repo=relations_repo,
        requests_repo=requests_repo,
        seq_allocator=seq_allocator,
        members_repo=members_repo,
    )

    await service.create_request(
        source_task.id,
        CreateRequestPayload(requested_team_id=target_team.id, suggested_title="Help us"),
        p,
    )

    persisted = [call.args[0] for call in notifications_repo.create.await_args_list]
    assert len(persisted) == 1
    note = persisted[0]
    assert isinstance(note, Notification)
    assert note.type is NotificationType.CROSS_TEAM_REQUEST
    assert note.user_id == manager.user_id
    assert note.source_member_id == p.member_id
    # Preview should name the public ids and the requester.
    assert "Alice" in note.preview
    assert "TASK-101" in note.preview


async def test_create_request_notifies_lead_and_dept_head(
    service: TaskService,
    task_repo: AsyncMock,
    members_repo: AsyncMock,
    relations_repo: AsyncMock,
    requests_repo: AsyncMock,
    teams_repo: AsyncMock,
    tenant_members_repo: AsyncMock,
    notifications_repo: AsyncMock,
    seq_allocator: AsyncMock,
    workspace_repo: AsyncMock,
) -> None:
    """All three leadership roles get rows when distinct: MANAGER,
    LEAD, and the department head walked via team_lookup."""
    p = make_principal(role=MemberRole.WORKSPACE_OWNER)
    source_task = make_task(workspace_id=p.workspace_id)
    target_team = _team(p.workspace_id)
    manager_user = uuid4()
    lead_user = uuid4()
    head_user = uuid4()
    manager = _member(workspace_id=p.workspace_id, user_id=manager_user)
    lead = _member(workspace_id=p.workspace_id, user_id=lead_user)
    dept_head_id = uuid4()
    dept_head = _member(workspace_id=p.workspace_id, member_id=dept_head_id, user_id=head_user)

    await _set_up_create_request(
        p=p,
        source_task=source_task,
        target_team=target_team,
        task_repo=task_repo,
        teams_repo=teams_repo,
        relations_repo=relations_repo,
        requests_repo=requests_repo,
        seq_allocator=seq_allocator,
        members_repo=members_repo,
    )
    # AFTER the helper's defaults so these overrides stick. Sequenced
    # side_effect: get_for_team_role is called for MANAGER then LEAD
    # in that order; pin both with a deterministic sequence.
    tenant_members_repo.get_for_team_role.side_effect = [manager, lead]
    teams_repo.get_department_head_for_team.return_value = dept_head_id
    requester_member = members_repo.get_by_id.return_value
    members_repo.get_by_id.side_effect = lambda mid: (
        dept_head if mid == dept_head_id else requester_member
    )

    await service.create_request(
        source_task.id,
        CreateRequestPayload(requested_team_id=target_team.id, suggested_title="Help us"),
        p,
    )

    recipient_user_ids = [
        call.args[0].user_id for call in notifications_repo.create.await_args_list
    ]
    expected = [manager_user, lead_user, head_user]
    assert recipient_user_ids == expected, (recipient_user_ids, expected)


async def test_create_request_excludes_requester_from_recipients(
    service: TaskService,
    task_repo: AsyncMock,
    members_repo: AsyncMock,
    relations_repo: AsyncMock,
    requests_repo: AsyncMock,
    teams_repo: AsyncMock,
    tenant_members_repo: AsyncMock,
    notifications_repo: AsyncMock,
    seq_allocator: AsyncMock,
    workspace_repo: AsyncMock,
) -> None:
    """A requester who happens to be on the target team's leadership
    (e.g. a workspace admin with multi-team membership) does not
    notify themselves."""
    p = make_principal(role=MemberRole.WORKSPACE_OWNER)
    source_task = make_task(workspace_id=p.workspace_id)
    target_team = _team(p.workspace_id)
    # Requester IS the MANAGER of the target team.
    self_manager = _member(
        workspace_id=p.workspace_id,
        member_id=p.member_id,
        team_id=target_team.id,
        team_role=TeamRole.MANAGER,
    )
    tenant_members_repo.get_for_team_role.side_effect = lambda team_id, role: (
        self_manager if role is TeamRole.MANAGER else None
    )

    await _set_up_create_request(
        p=p,
        source_task=source_task,
        target_team=target_team,
        task_repo=task_repo,
        teams_repo=teams_repo,
        relations_repo=relations_repo,
        requests_repo=requests_repo,
        seq_allocator=seq_allocator,
        members_repo=members_repo,
    )
    # Workspace-owner fallback queries list_for_workspace; nobody
    # should be there either (or be excluded if it's the requester).
    tenant_members_repo.list_for_workspace.return_value = ([], 0)

    await service.create_request(
        source_task.id,
        CreateRequestPayload(requested_team_id=target_team.id, suggested_title="Help us"),
        p,
    )

    notifications_repo.create.assert_not_called()


async def test_create_request_falls_back_to_workspace_owners_for_leaderless_team(
    service: TaskService,
    task_repo: AsyncMock,
    members_repo: AsyncMock,
    relations_repo: AsyncMock,
    requests_repo: AsyncMock,
    teams_repo: AsyncMock,
    tenant_members_repo: AsyncMock,
    notifications_repo: AsyncMock,
    seq_allocator: AsyncMock,
    workspace_repo: AsyncMock,
) -> None:
    """The leaderless-team safety net. A target team with no MANAGER,
    no LEAD, no department head must NEVER produce a silent request.
    Fall back to notifying the workspace owners so an admin can route
    the work manually."""
    p = make_principal(role=MemberRole.WORKSPACE_OWNER)
    source_task = make_task(workspace_id=p.workspace_id)
    target_team = _team(p.workspace_id)
    owner_a = _member(workspace_id=p.workspace_id, role=MemberRole.WORKSPACE_OWNER, priority=1)
    owner_b = _member(workspace_id=p.workspace_id, role=MemberRole.WORKSPACE_OWNER, priority=1)

    await _set_up_create_request(
        p=p,
        source_task=source_task,
        target_team=target_team,
        task_repo=task_repo,
        teams_repo=teams_repo,
        relations_repo=relations_repo,
        requests_repo=requests_repo,
        seq_allocator=seq_allocator,
        members_repo=members_repo,
    )
    # AFTER the helper: no team leadership exists, but two workspace
    # owners do (the fallback path).
    tenant_members_repo.get_for_team_role.return_value = None
    teams_repo.get_department_head_for_team.return_value = None
    tenant_members_repo.list_for_workspace.return_value = ([owner_a, owner_b], 2)

    await service.create_request(
        source_task.id,
        CreateRequestPayload(requested_team_id=target_team.id, suggested_title="Help us"),
        p,
    )

    # The fallback query was invoked with role=OWNER filter.
    tenant_members_repo.list_for_workspace.assert_awaited_once()
    call_kwargs = tenant_members_repo.list_for_workspace.await_args.kwargs
    assert call_kwargs["role"] is MemberRole.WORKSPACE_OWNER

    recipients = {call.args[0].user_id for call in notifications_repo.create.await_args_list}
    assert recipients == {owner_a.user_id, owner_b.user_id}


async def test_create_request_excludes_agent_members_from_recipients(
    service: TaskService,
    task_repo: AsyncMock,
    members_repo: AsyncMock,
    relations_repo: AsyncMock,
    requests_repo: AsyncMock,
    teams_repo: AsyncMock,
    tenant_members_repo: AsyncMock,
    notifications_repo: AsyncMock,
    seq_allocator: AsyncMock,
    workspace_repo: AsyncMock,
) -> None:
    """AGENT members don't have a user_id and can't receive
    notifications. An agent holding a team-leadership role just falls
    out of the recipient set quietly; the fallback fires if that
    empties leadership entirely."""
    p = make_principal(role=MemberRole.WORKSPACE_OWNER)
    source_task = make_task(workspace_id=p.workspace_id)
    target_team = _team(p.workspace_id)
    # MANAGER is an AGENT (no user_id).
    agent_manager = _member(
        workspace_id=p.workspace_id,
        team_id=target_team.id,
        team_role=TeamRole.MANAGER,
        member_type=MemberType.AGENT,
    )
    owner = _member(workspace_id=p.workspace_id, role=MemberRole.WORKSPACE_OWNER, priority=1)

    await _set_up_create_request(
        p=p,
        source_task=source_task,
        target_team=target_team,
        task_repo=task_repo,
        teams_repo=teams_repo,
        relations_repo=relations_repo,
        requests_repo=requests_repo,
        seq_allocator=seq_allocator,
        members_repo=members_repo,
    )
    tenant_members_repo.get_for_team_role.side_effect = [agent_manager, None]
    tenant_members_repo.list_for_workspace.return_value = ([owner], 1)

    await service.create_request(
        source_task.id,
        CreateRequestPayload(requested_team_id=target_team.id, suggested_title="Help us"),
        p,
    )

    # Agent manager didn't receive a row; fallback to owners did.
    recipient_ids = [call.args[0].user_id for call in notifications_repo.create.await_args_list]
    assert recipient_ids == [owner.user_id]


async def test_create_request_does_not_crash_when_workspace_state_is_pathological(
    service: TaskService,
    task_repo: AsyncMock,
    members_repo: AsyncMock,
    relations_repo: AsyncMock,
    requests_repo: AsyncMock,
    teams_repo: AsyncMock,
    tenant_members_repo: AsyncMock,
    notifications_repo: AsyncMock,
    seq_allocator: AsyncMock,
    workspace_repo: AsyncMock,
) -> None:
    """Defensive pin for an *unreachable* state in production: a target
    team with no leadership AND a workspace with zero owners. The
    last-owner invariant chain (workspace creation always mints an
    OWNER + the last-owner protection in update_member_profile +
    the last-active-owner protection in set_member_suspension) means
    no live workspace can have zero active owners — so the leaderless
    fallback ALWAYS finds at least one recipient. This test guards
    against a future regression that touches the recipient pipeline:
    if the impossible somehow happens, create_request must not raise
    (the task + relation + request row have already persisted by the
    time notification runs)."""
    p = make_principal(role=MemberRole.WORKSPACE_OWNER)
    source_task = make_task(workspace_id=p.workspace_id)
    target_team = _team(p.workspace_id)

    await _set_up_create_request(
        p=p,
        source_task=source_task,
        target_team=target_team,
        task_repo=task_repo,
        teams_repo=teams_repo,
        relations_repo=relations_repo,
        requests_repo=requests_repo,
        seq_allocator=seq_allocator,
        members_repo=members_repo,
    )
    tenant_members_repo.get_for_team_role.return_value = None
    tenant_members_repo.list_for_workspace.return_value = ([], 0)

    # Doesn't raise.
    await service.create_request(
        source_task.id,
        CreateRequestPayload(requested_team_id=target_team.id, suggested_title="Help us"),
        p,
    )

    notifications_repo.create.assert_not_called()


# ---------- Bug 3: cross_team_origin denormalisation ----------


async def test_resolve_cross_team_origin_returns_ref_for_auto_minted_task(
    service: TaskService,
    task_repo: AsyncMock,
    members_repo: AsyncMock,
    requests_repo: AsyncMock,
    workspace_repo: AsyncMock,
) -> None:
    """A task that is some request's ``fulfilled_task_id`` resolves to
    a CrossTeamOriginRef carrying the source task's public_id and the
    requester's name."""
    source_workspace_id = uuid4()
    source_task = make_task(workspace_id=source_workspace_id)
    target_task_id = uuid4()
    request_id = uuid4()
    requester_member_id = uuid4()
    requests_repo.list_fulfilled_by_task_ids.return_value = [
        TaskRequest(
            id=request_id,
            source_task_id=source_task.id,
            requested_team_id=uuid4(),
            requester_member_id=requester_member_id,
            suggested_title="Need help",
            suggested_description=None,
            justification=None,
            status=RequestStatus.FULFILLED,
            fulfilled_task_id=target_task_id,
            resolver_member_id=requester_member_id,
            created_at=datetime.now(UTC),
            resolved_at=datetime.now(UTC),
        )
    ]
    task_repo.get_by_id.return_value = source_task
    # workspace_prefix lookup
    from app.domain.entities import Workspace

    workspace_repo.get_by_id.return_value = Workspace(
        id=source_workspace_id,
        name="src",
        slug="src",
        task_prefix="ENG",
        next_task_seq=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    members_repo.get_by_id.return_value = Member(
        id=requester_member_id,
        workspace_id=source_workspace_id,
        type=MemberType.HUMAN,
        name="Alice",
        email="alice@example.com",
        priority=3,
        user_id=uuid4(),
    )

    origin = await service._resolve_cross_team_origin(target_task_id)

    assert origin is not None
    assert origin.request_id == request_id
    assert origin.source_task_id == source_task.id
    assert origin.source_task_public_id.startswith("ENG-")
    assert origin.requester_name == "Alice"


async def test_resolve_cross_team_origin_is_null_for_normal_task(
    service: TaskService, requests_repo: AsyncMock
) -> None:
    """A task that isn't any request's fulfilled_task_id resolves to
    None — drives the absence-of-marker on the board card."""
    requests_repo.list_fulfilled_by_task_ids.return_value = []

    origin = await service._resolve_cross_team_origin(uuid4())

    assert origin is None
    requests_repo.list_fulfilled_by_task_ids.assert_awaited_once()


async def test_cross_team_origin_resolver_batches_with_single_query(
    service: TaskService,
    requests_repo: AsyncMock,
    task_repo: AsyncMock,
    members_repo: AsyncMock,
    workspace_repo: AsyncMock,
) -> None:
    """Critical perf guarantee: the batch resolver makes exactly ONE
    ``list_fulfilled_by_task_ids`` call regardless of the input size.
    An N+1 here would regress the kanban board, which renders many
    tasks per page. Pinned with assert_awaited_once."""
    task_ids = [uuid4() for _ in range(10)]
    requests_repo.list_fulfilled_by_task_ids.return_value = []

    await service._resolve_cross_team_origin_map(task_ids)

    requests_repo.list_fulfilled_by_task_ids.assert_awaited_once_with(task_ids)


async def test_cross_team_origin_resolver_empty_list_skips_query(
    service: TaskService, requests_repo: AsyncMock
) -> None:
    """An empty task-id list short-circuits without hitting the repo
    (board view with no rows; tenant with no tasks at all)."""
    result = await service._resolve_cross_team_origin_map([])

    assert result == {}
    requests_repo.list_fulfilled_by_task_ids.assert_not_called()
