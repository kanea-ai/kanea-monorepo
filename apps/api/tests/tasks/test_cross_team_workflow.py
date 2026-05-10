"""Section 3 tests: cross-team rule + request lifecycle.

Two surfaces:
1. POST /tasks rejects a non-admin / non-leadership member trying to
   target another team's board (CrossTeamForbiddenError -> 403).
2. The request workflow: a MEMBER files a request from their source
   task; their team's MANAGER / LEAD fulfills (mints target task +
   BLOCKS relation) or rejects.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.application.tasks.schemas import (
    CreateRequestPayload,
    CreateTaskRequest,
    FulfillRequestPayload,
    RejectRequestPayload,
)
from app.application.tasks.service import TaskService
from app.domain.entities import Member, TaskRequest, Team
from app.domain.enums import (
    MemberRole,
    MemberType,
    RequestStatus,
    TaskRelationType,
    TeamRole,
)
from app.domain.exceptions import (
    CrossTeamForbiddenError,
    TaskRequestAlreadyResolvedError,
    TaskRequestForbiddenError,
    TaskRequestNotFoundError,
)
from tests.tasks.factories import make_principal, make_task


def _team(workspace_id, name="Backend") -> Team:
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
    team_id=None,
    team_role: TeamRole | None = None,
    role: MemberRole = MemberRole.WORKSPACE_USER,
) -> Member:
    return Member(
        id=member_id or uuid4(),
        workspace_id=workspace_id,
        type=MemberType.HUMAN,
        name="alice",
        email="a@example.com",
        priority=3,
        role=role,
        team_id=team_id,
        team_role=team_role,
    )


@pytest.fixture
def task_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def members() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def projects_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def teams_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def relations() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def requests_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(
    task_repo: AsyncMock,
    members: AsyncMock,
    workspace_repo: AsyncMock,
    seq_allocator: AsyncMock,
    projects_repo: AsyncMock,
    teams_repo: AsyncMock,
    relations: AsyncMock,
    requests_repo: AsyncMock,
) -> TaskService:
    return TaskService(
        tasks=task_repo,
        members=members,
        workspaces=workspace_repo,
        seq_allocator=seq_allocator,
        projects=projects_repo,
        team_lookup=teams_repo,
        relations=relations,
        requests=requests_repo,
    )


# ---------- cross-team rule on POST /tasks ----------


async def test_member_cannot_target_another_team(
    service: TaskService,
    members: AsyncMock,
    teams_repo: AsyncMock,
    task_repo: AsyncMock,
) -> None:
    p = make_principal(role=MemberRole.WORKSPACE_USER)
    other_team = _team(p.workspace_id)
    teams_repo.get_by_id.return_value = other_team
    members.get_by_id.return_value = _member(
        workspace_id=p.workspace_id,
        member_id=p.member_id,
        team_id=uuid4(),  # member's team is different
        team_role=TeamRole.MEMBER,
    )

    with pytest.raises(CrossTeamForbiddenError):
        await service.create(CreateTaskRequest(title="x", team_id=other_team.id), p)
    task_repo.create.assert_not_called()


async def test_member_can_target_own_team(
    service: TaskService,
    members: AsyncMock,
    teams_repo: AsyncMock,
    task_repo: AsyncMock,
) -> None:
    p = make_principal(role=MemberRole.WORKSPACE_USER)
    own_team = _team(p.workspace_id)
    teams_repo.get_by_id.return_value = own_team
    members.get_by_id.return_value = _member(
        workspace_id=p.workspace_id,
        member_id=p.member_id,
        team_id=own_team.id,
        team_role=TeamRole.MEMBER,
    )
    task_repo.create.side_effect = lambda t: t

    await service.create(CreateTaskRequest(title="x", team_id=own_team.id), p)
    task_repo.create.assert_awaited_once()


async def test_lead_can_target_other_team(
    service: TaskService,
    members: AsyncMock,
    teams_repo: AsyncMock,
    task_repo: AsyncMock,
) -> None:
    """Leadership rank bypasses the same-team check — that's the
    escalation path for cross-team work."""
    p = make_principal(role=MemberRole.WORKSPACE_USER)
    own_team = _team(p.workspace_id, name="A")
    other_team = _team(p.workspace_id, name="B")
    teams_repo.get_by_id.return_value = other_team
    members.get_by_id.return_value = _member(
        workspace_id=p.workspace_id,
        member_id=p.member_id,
        team_id=own_team.id,
        team_role=TeamRole.LEAD,
    )
    task_repo.create.side_effect = lambda t: t

    await service.create(CreateTaskRequest(title="x", team_id=other_team.id), p)
    task_repo.create.assert_awaited_once()


async def test_admin_can_target_any_team_without_membership(
    service: TaskService,
    teams_repo: AsyncMock,
    task_repo: AsyncMock,
) -> None:
    p = make_principal(role=MemberRole.WORKSPACE_ADMIN)
    target = _team(p.workspace_id)
    teams_repo.get_by_id.return_value = target
    task_repo.create.side_effect = lambda t: t

    await service.create(CreateTaskRequest(title="x", team_id=target.id), p)
    task_repo.create.assert_awaited_once()


# ---------- request creation ----------


async def test_member_can_request_on_own_task(
    service: TaskService,
    task_repo: AsyncMock,
    teams_repo: AsyncMock,
    requests_repo: AsyncMock,
    relations: AsyncMock,
    seq_allocator: AsyncMock,
    members: AsyncMock,
) -> None:
    """Auto-fulfill flow: filing the request mints the target task
    immediately, links source ← target, and the request row stores
    as FULFILLED with the new task id."""
    p = make_principal(role=MemberRole.WORKSPACE_USER)
    source = make_task(workspace_id=p.workspace_id, created_by_id=p.member_id)
    target_team = _team(p.workspace_id)
    task_repo.get_by_id.return_value = source
    task_repo.create.side_effect = lambda t: t
    teams_repo.get_by_id.return_value = target_team
    members.get_by_id.return_value = _member(workspace_id=p.workspace_id, member_id=p.member_id)
    seq_allocator.allocate_next_task_seq.return_value = (42, "DEVOPS")
    requests_repo.create.side_effect = lambda r: r

    response = await service.create_request(
        source.id,
        CreateRequestPayload(
            requested_team_id=target_team.id,
            suggested_title="please help",
            justification="we hit an API",
        ),
        p,
    )

    # Target task minted on the right team.
    task_repo.create.assert_awaited_once()
    minted = task_repo.create.call_args[0][0]
    assert minted.team_id == target_team.id
    assert minted.title == "please help"

    # Source ← target relation, default BLOCKS.
    relations.create.assert_awaited_once()
    rel = relations.create.call_args[0][0]
    assert rel.source_task_id == minted.id
    assert rel.target_task_id == source.id
    assert rel.relation_type is TaskRelationType.BLOCKS

    # Request row recorded as FULFILLED at creation, pointing at the
    # newly minted task.
    assert response.status is RequestStatus.FULFILLED
    assert response.fulfilled_task_id == minted.id
    assert response.requested_team_id == target_team.id


async def test_request_with_relates_to_does_not_block_source(
    service: TaskService,
    task_repo: AsyncMock,
    teams_repo: AsyncMock,
    requests_repo: AsyncMock,
    relations: AsyncMock,
    seq_allocator: AsyncMock,
    members: AsyncMock,
) -> None:
    """Choosing RELATES_TO instead of BLOCKS still mints the target
    task and links the two, but skips the BLOCKED activity entry on
    the source — the source isn't being held up by the new task."""
    p = make_principal(role=MemberRole.WORKSPACE_USER)
    source = make_task(workspace_id=p.workspace_id, created_by_id=p.member_id)
    target_team = _team(p.workspace_id)
    task_repo.get_by_id.return_value = source
    task_repo.create.side_effect = lambda t: t
    teams_repo.get_by_id.return_value = target_team
    members.get_by_id.return_value = _member(workspace_id=p.workspace_id, member_id=p.member_id)
    seq_allocator.allocate_next_task_seq.return_value = (43, "DEVOPS")
    requests_repo.create.side_effect = lambda r: r

    await service.create_request(
        source.id,
        CreateRequestPayload(
            requested_team_id=target_team.id,
            suggested_title="just FYI",
            relation_type=TaskRelationType.RELATES_TO,
        ),
        p,
    )
    rel = relations.create.call_args[0][0]
    assert rel.relation_type is TaskRelationType.RELATES_TO


async def test_member_cannot_request_on_someone_elses_task(
    service: TaskService,
    task_repo: AsyncMock,
    teams_repo: AsyncMock,
    requests_repo: AsyncMock,
) -> None:
    p = make_principal(role=MemberRole.WORKSPACE_USER)
    other_owner = uuid4()
    # Source task isn't created by or assigned to me.
    source = make_task(
        workspace_id=p.workspace_id, created_by_id=other_owner, assignee_id=other_owner
    )
    target_team = _team(p.workspace_id)
    task_repo.get_by_id.return_value = source
    teams_repo.get_by_id.return_value = target_team

    with pytest.raises(TaskRequestForbiddenError):
        await service.create_request(
            source.id,
            CreateRequestPayload(requested_team_id=target_team.id, suggested_title="hi"),
            p,
        )
    requests_repo.create.assert_not_called()


# ---------- fulfill ----------


def _request(
    *,
    source_task_id,
    requested_team_id,
    requester_id=None,
    status=RequestStatus.PENDING,
) -> TaskRequest:
    now = datetime.now(UTC)
    return TaskRequest(
        id=uuid4(),
        source_task_id=source_task_id,
        requested_team_id=requested_team_id,
        requester_member_id=requester_id or uuid4(),
        suggested_title="ship the thing",
        suggested_description=None,
        justification=None,
        status=status,
        created_at=now,
        updated_at=now,
    )


async def test_lead_on_source_team_can_fulfill(
    service: TaskService,
    task_repo: AsyncMock,
    members: AsyncMock,
    requests_repo: AsyncMock,
    relations: AsyncMock,
    seq_allocator: AsyncMock,
) -> None:
    """Fulfill mints a target task on requested_team_id and creates a
    BLOCKS relation pointing at the source task."""
    p = make_principal(role=MemberRole.WORKSPACE_USER)
    source_team = _team(p.workspace_id, name="A")
    target_team = _team(p.workspace_id, name="B")
    source = make_task(workspace_id=p.workspace_id, created_by_id=uuid4())
    source.team_id = source_team.id
    request_row = _request(source_task_id=source.id, requested_team_id=target_team.id)

    requests_repo.get_by_id.return_value = request_row
    task_repo.get_by_id.return_value = source
    # Requester is a LEAD on source_team
    members.get_by_id.return_value = _member(
        workspace_id=p.workspace_id,
        member_id=p.member_id,
        team_id=source_team.id,
        team_role=TeamRole.LEAD,
    )
    seq_allocator.allocate_next_task_seq.return_value = (42, "ACME")
    task_repo.create.side_effect = lambda t: t
    requests_repo.mark_fulfilled.side_effect = lambda *_a, **_kw: TaskRequest(
        id=request_row.id,
        source_task_id=request_row.source_task_id,
        requested_team_id=request_row.requested_team_id,
        requester_member_id=request_row.requester_member_id,
        suggested_title=request_row.suggested_title,
        suggested_description=None,
        justification=None,
        status=RequestStatus.FULFILLED,
        fulfilled_task_id=_kw["fulfilled_task_id"],
        resolver_member_id=_kw["resolver_member_id"],
        resolved_at=_kw["resolved_at"],
        created_at=request_row.created_at,
        updated_at=request_row.updated_at,
    )

    response = await service.fulfill_request(request_row.id, FulfillRequestPayload(priority=5), p)
    assert response.status is RequestStatus.FULFILLED

    # Target task created on requested_team_id.
    persisted_task = task_repo.create.await_args.args[0]
    assert persisted_task.team_id == target_team.id
    assert persisted_task.title == "ship the thing"
    # BLOCKS relation: target task BLOCKS source task.
    persisted_relation = relations.create.await_args.args[0]
    assert persisted_relation.source_task_id == persisted_task.id
    assert persisted_relation.target_task_id == source.id
    assert persisted_relation.relation_type is TaskRelationType.BLOCKS


async def test_plain_member_on_source_team_cannot_fulfill(
    service: TaskService,
    task_repo: AsyncMock,
    members: AsyncMock,
    requests_repo: AsyncMock,
) -> None:
    p = make_principal(role=MemberRole.WORKSPACE_USER)
    source_team = _team(p.workspace_id)
    target_team = _team(p.workspace_id, name="B")
    source = make_task(workspace_id=p.workspace_id)
    source.team_id = source_team.id

    requests_repo.get_by_id.return_value = _request(
        source_task_id=source.id, requested_team_id=target_team.id
    )
    task_repo.get_by_id.return_value = source
    members.get_by_id.return_value = _member(
        workspace_id=p.workspace_id,
        member_id=p.member_id,
        team_id=source_team.id,
        team_role=TeamRole.MEMBER,  # not leadership
    )

    with pytest.raises(TaskRequestForbiddenError):
        await service.fulfill_request(uuid4(), FulfillRequestPayload(), p)


async def test_already_resolved_request_cannot_be_refulfilled(
    service: TaskService,
    task_repo: AsyncMock,
    requests_repo: AsyncMock,
) -> None:
    p = make_principal(role=MemberRole.WORKSPACE_ADMIN)
    source = make_task(workspace_id=p.workspace_id)
    requests_repo.get_by_id.return_value = _request(
        source_task_id=source.id,
        requested_team_id=uuid4(),
        status=RequestStatus.FULFILLED,
    )
    task_repo.get_by_id.return_value = source

    with pytest.raises(TaskRequestAlreadyResolvedError):
        await service.fulfill_request(uuid4(), FulfillRequestPayload(), p)


# ---------- reject ----------


async def test_lead_can_reject(
    service: TaskService,
    task_repo: AsyncMock,
    members: AsyncMock,
    requests_repo: AsyncMock,
) -> None:
    p = make_principal(role=MemberRole.WORKSPACE_USER)
    source_team = _team(p.workspace_id)
    source = make_task(workspace_id=p.workspace_id)
    source.team_id = source_team.id
    request_row = _request(source_task_id=source.id, requested_team_id=uuid4())

    requests_repo.get_by_id.return_value = request_row
    task_repo.get_by_id.return_value = source
    members.get_by_id.return_value = _member(
        workspace_id=p.workspace_id,
        member_id=p.member_id,
        team_id=source_team.id,
        team_role=TeamRole.MANAGER,
    )
    requests_repo.mark_rejected.side_effect = lambda *_a, **kw: TaskRequest(
        id=request_row.id,
        source_task_id=source.id,
        requested_team_id=request_row.requested_team_id,
        requester_member_id=request_row.requester_member_id,
        suggested_title=request_row.suggested_title,
        suggested_description=None,
        justification=None,
        status=RequestStatus.REJECTED,
        reject_reason=kw["reason"],
        resolver_member_id=kw["resolver_member_id"],
        resolved_at=kw["resolved_at"],
        created_at=request_row.created_at,
        updated_at=request_row.updated_at,
    )

    response = await service.reject_request(
        request_row.id, RejectRequestPayload(reason="not now"), p
    )
    assert response.status is RequestStatus.REJECTED
    assert response.reject_reason == "not now"


async def test_unknown_request_404s(service: TaskService, requests_repo: AsyncMock) -> None:
    p = make_principal(role=MemberRole.WORKSPACE_ADMIN)
    requests_repo.get_by_id.return_value = None
    with pytest.raises(TaskRequestNotFoundError):
        await service.fulfill_request(uuid4(), FulfillRequestPayload(), p)


async def test_cross_tenant_request_404s(
    service: TaskService,
    requests_repo: AsyncMock,
    task_repo: AsyncMock,
) -> None:
    """Request anchored to a task in another workspace surfaces as
    not-found — same shape as truly-missing so cross-tenant probing
    leaks nothing."""
    p = make_principal(role=MemberRole.WORKSPACE_ADMIN)
    other_workspace = uuid4()
    source = make_task(workspace_id=other_workspace)
    requests_repo.get_by_id.return_value = _request(
        source_task_id=source.id, requested_team_id=uuid4()
    )
    task_repo.get_by_id.return_value = source

    with pytest.raises(TaskRequestNotFoundError):
        await service.reject_request(uuid4(), RejectRequestPayload(reason="x"), p)
