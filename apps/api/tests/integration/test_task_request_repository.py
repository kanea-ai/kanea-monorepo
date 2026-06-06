"""Integration tests for the cross-team request auto-fulfil path.

Run against a real Postgres instance — see tests/integration/conftest.

These tests exist because of a production bug that the rest of the
suite could not catch: ``SqlAlchemyTaskRequestRepository.create()``
silently dropped ``fulfilled_task_id`` / ``resolver_member_id`` /
``resolved_at`` when persisting a new request. The auto-fulfil path
(``TaskService.create_request``) mints the target task and stores the
request already in the FULFILLED state carrying those fields — but the
row landed with a NULL ``fulfilled_task_id``. Consequences in prod:
the team-inbox row could not link to the minted task, and the
``cross_team_origin`` marker never resolved (it joins tasks on
``fulfilled_task_id``).

It shipped because of the same test-blind-spot family as the security
findings: the unit tests mock the repository (so a repo-layer omission
is invisible), and the only *integration* coverage of request
resolution exercised the **manual** ``mark_fulfilled`` path — which
sets the fields correctly — never the **auto-fulfil-on-create** path.
This module closes that gap by driving ``create_request`` against a
real repository and asserting the persisted row and the
``cross_team_origin`` resolution.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.tasks.schemas import CreateRequestPayload, Principal
from app.application.tasks.service import TaskService
from app.domain.entities import Task
from app.domain.enums import MemberRole, MemberType, RequestStatus, TaskStatus
from app.infrastructure.db.models import MemberModel, TeamModel, UserModel, WorkspaceModel
from app.infrastructure.repositories.member import SqlAlchemyMemberRepository
from app.infrastructure.repositories.task import SqlAlchemyTaskRepository
from app.infrastructure.repositories.task_relation import SqlAlchemyTaskRelationRepository
from app.infrastructure.repositories.task_request import SqlAlchemyTaskRequestRepository
from app.infrastructure.repositories.team import SqlAlchemyTeamRepository
from app.infrastructure.repositories.workspace import SqlAlchemyWorkspaceRepository


@pytest.fixture
async def seeded(pg_session: AsyncSession) -> dict[str, UUID]:
    """Workspace + owner (HUMAN, so it can act as requester) + a target
    team + a source task. ``next_task_seq`` starts at 2 so the
    auto-minted target task (seq allocated by create_request) cannot
    collide with the source task's seq=1 on the (workspace_id, seq)
    unique index."""
    ws = WorkspaceModel(
        id=uuid4(),
        name=f"WS-{uuid4().hex[:6]}",
        slug=f"ws-{uuid4().hex[:6]}",
        task_prefix="TST",
        next_task_seq=2,
    )
    pg_session.add(ws)
    await pg_session.flush()

    owner_user = UserModel(
        id=uuid4(),
        email=f"owner-{uuid4().hex[:6]}@example.com",
        full_name="Owner",
        password_hash="bcrypt$placeholder",  # pragma: allowlist secret
    )
    pg_session.add(owner_user)
    await pg_session.flush()

    owner = MemberModel(
        id=uuid4(),
        workspace_id=ws.id,
        user_id=owner_user.id,
        type=MemberType.HUMAN,
        name="Owner",
        email=owner_user.email,
        priority=1,
        role=MemberRole.WORKSPACE_OWNER,
    )
    pg_session.add(owner)
    await pg_session.flush()

    target_team = TeamModel(id=uuid4(), workspace_id=ws.id, name="DevOps")
    pg_session.add(target_team)
    await pg_session.flush()

    source_task = await SqlAlchemyTaskRepository(pg_session).create(
        Task(
            id=uuid4(),
            workspace_id=ws.id,
            created_by_id=owner.id,
            title="Source feature task",
            status=TaskStatus.IN_PROGRESS,
            priority=0,
            seq=1,
            assignee_id=owner.id,
        )
    )

    return {
        "workspace_id": ws.id,
        "owner_id": owner.id,
        "target_team_id": target_team.id,
        "source_task_id": source_task.id,
    }


def _service(session: AsyncSession) -> TaskService:
    """A TaskService wired with real repositories for the create_request
    path. The notification side (notifications / tenant_members) is left
    unwired so ``_notify_cross_team_request`` no-ops — these tests are
    about persistence + cross_team_origin resolution, not delivery."""
    return TaskService(
        tasks=SqlAlchemyTaskRepository(session),
        members=SqlAlchemyMemberRepository(session),
        workspaces=SqlAlchemyWorkspaceRepository(session),
        seq_allocator=SqlAlchemyWorkspaceRepository(session),
        relations=SqlAlchemyTaskRelationRepository(session),
        requests=SqlAlchemyTaskRequestRepository(session),
        team_lookup=SqlAlchemyTeamRepository(session),
        activities=None,
        notifications=None,
        tenant_members=None,
    )


async def test_create_request_persists_resolution_fields(
    pg_session: AsyncSession, seeded: dict[str, UUID]
) -> None:
    """The regression test whose absence shipped the bug: after
    create_request auto-fulfils, the PERSISTED request row must carry
    fulfilled_task_id, resolver_member_id and resolved_at — not just the
    in-memory entity. Re-read from the DB through a fresh repo to prove
    the columns were written, not merely echoed back."""
    service = _service(pg_session)
    principal = Principal(
        member_id=seeded["owner_id"],
        workspace_id=seeded["workspace_id"],
        type=MemberType.HUMAN,
        priority=1,
        scope="human",
        role=MemberRole.WORKSPACE_OWNER,
    )
    payload = CreateRequestPayload(
        requested_team_id=seeded["target_team_id"],
        suggested_title="Add endpoint to the rate-limit allow-list",
        suggested_description="DevOps gateway change",
        justification="Only DevOps can deploy gateway config",
    )

    resp = await service.create_request(seeded["source_task_id"], payload, principal)
    assert resp.status == RequestStatus.FULFILLED
    assert resp.fulfilled_task_id is not None

    # Re-read the row from Postgres to confirm the columns persisted.
    persisted = await SqlAlchemyTaskRequestRepository(pg_session).get_by_id(resp.id)
    assert persisted is not None
    assert persisted.fulfilled_task_id == resp.fulfilled_task_id  # was NULL before the fix
    assert persisted.resolver_member_id == seeded["owner_id"]
    assert persisted.resolved_at is not None


async def test_create_request_minted_task_resolves_cross_team_origin(
    pg_session: AsyncSession, seeded: dict[str, UUID]
) -> None:
    """The user-visible symptom: the auto-minted target task must resolve
    a cross_team_origin marker back to the source. This depends on
    fulfilled_task_id being persisted (the resolver joins tasks on it)
    and on list_fulfilled_by_task_ids returning the row."""
    service = _service(pg_session)
    principal = Principal(
        member_id=seeded["owner_id"],
        workspace_id=seeded["workspace_id"],
        type=MemberType.HUMAN,
        priority=1,
        scope="human",
        role=MemberRole.WORKSPACE_OWNER,
    )
    payload = CreateRequestPayload(
        requested_team_id=seeded["target_team_id"],
        suggested_title="Add endpoint to the rate-limit allow-list",
        suggested_description="DevOps gateway change",
        justification="Only DevOps can deploy gateway config",
    )

    resp = await service.create_request(seeded["source_task_id"], payload, principal)
    minted_task_id = resp.fulfilled_task_id
    assert minted_task_id is not None

    # Batch resolver (the one list flows use) must find the request.
    rows = await SqlAlchemyTaskRequestRepository(pg_session).list_fulfilled_by_task_ids(
        [minted_task_id]
    )
    assert [r.id for r in rows] == [resp.id]

    # And the single-task resolver must build a populated marker.
    origin = await service._resolve_cross_team_origin(minted_task_id)
    assert origin is not None
    assert origin.source_task_id == seeded["source_task_id"]
    assert origin.source_task_public_id == "TST-001"
    assert origin.requester_member_id == seeded["owner_id"]
