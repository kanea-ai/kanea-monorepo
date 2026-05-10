"""Integration tests for ``SqlAlchemyTaskRepository``.

Run against a real Postgres instance — see tests/integration/conftest.
The repo file uses Postgres-specific column types (PgEnum, JSONB) so
SQLite-backed unit tests can't reach it. These tests cover every
public method on the repo so the SQL paths are exercised.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import Task
from app.domain.enums import MemberRole, MemberType, ProjectStatus, TaskStatus
from app.domain.exceptions import TaskNotFoundError
from app.infrastructure.db.models import (
    DepartmentModel,
    MemberModel,
    ProjectModel,
    TeamModel,
    UserModel,
    WorkspaceModel,
)
from app.infrastructure.repositories.task import SqlAlchemyTaskRepository

# ---------- fixtures ----------


@pytest.fixture
def repo(pg_session: AsyncSession) -> SqlAlchemyTaskRepository:
    return SqlAlchemyTaskRepository(pg_session)


@pytest.fixture
async def seeded(pg_session: AsyncSession) -> dict[str, UUID]:
    """Seed a workspace + creator member + a couple of teams + a
    project. Returns the ids the tests reuse."""
    workspace = WorkspaceModel(
        id=uuid4(),
        name=f"WS-{uuid4().hex[:6]}",
        slug=f"ws-{uuid4().hex[:6]}",
        task_prefix="TST",
        next_task_seq=1,
    )
    pg_session.add(workspace)
    await pg_session.flush()

    # HUMAN members require a User row (CHECK constraint
    # ``members_human_has_user`` enforces this). Mint one per
    # member; the password_hash placeholder satisfies the
    # ``users_at_least_one_secret`` check.
    creator_user = UserModel(
        id=uuid4(),
        email=f"creator-{uuid4().hex[:6]}@example.com",
        full_name="Creator",
        password_hash="bcrypt$placeholder",  # pragma: allowlist secret
    )
    assignee_user = UserModel(
        id=uuid4(),
        email=f"assignee-{uuid4().hex[:6]}@example.com",
        full_name="Assignee",
        password_hash="bcrypt$placeholder",  # pragma: allowlist secret
    )
    pg_session.add_all([creator_user, assignee_user])
    await pg_session.flush()

    creator = MemberModel(
        id=uuid4(),
        workspace_id=workspace.id,
        user_id=creator_user.id,
        type=MemberType.HUMAN,
        name="Creator",
        email=creator_user.email,
        priority=1,
        role=MemberRole.WORKSPACE_OWNER,
    )
    assignee = MemberModel(
        id=uuid4(),
        workspace_id=workspace.id,
        user_id=assignee_user.id,
        type=MemberType.HUMAN,
        name="Assignee",
        email=assignee_user.email,
        priority=5,
        role=MemberRole.WORKSPACE_USER,
    )
    pg_session.add_all([creator, assignee])
    await pg_session.flush()

    department = DepartmentModel(
        id=uuid4(),
        workspace_id=workspace.id,
        name="Engineering",
    )
    pg_session.add(department)
    await pg_session.flush()

    team_a = TeamModel(
        id=uuid4(),
        workspace_id=workspace.id,
        name="Backend",
        department_id=department.id,
    )
    team_b = TeamModel(
        id=uuid4(),
        workspace_id=workspace.id,
        name="Frontend",
    )
    pg_session.add_all([team_a, team_b])
    await pg_session.flush()

    project = ProjectModel(
        id=uuid4(),
        workspace_id=workspace.id,
        name="P1",
        description=None,
        status=ProjectStatus.ACTIVE,
    )
    pg_session.add(project)
    await pg_session.flush()

    return {
        "workspace_id": workspace.id,
        "creator_id": creator.id,
        "assignee_id": assignee.id,
        "team_a_id": team_a.id,
        "team_b_id": team_b.id,
        "project_id": project.id,
    }


def _task_entity(
    *,
    workspace_id: UUID,
    creator_id: UUID,
    title: str = "demo",
    status: TaskStatus = TaskStatus.PENDING,
    priority: int = 5,
    seq: int = 1,
    assignee_id: UUID | None = None,
    project_id: UUID | None = None,
    team_id: UUID | None = None,
    is_blocked: bool = False,
    blocked_reason: str | None = None,
) -> Task:
    now = datetime.now(UTC)
    return Task(
        id=uuid4(),
        workspace_id=workspace_id,
        created_by_id=creator_id,
        title=title,
        status=status,
        priority=priority,
        seq=seq,
        assignee_id=assignee_id,
        project_id=project_id,
        team_id=team_id,
        is_blocked=is_blocked,
        blocked_reason=blocked_reason,
        created_at=now,
        updated_at=now,
    )


# ---------- create + get_by_id + list_by_ids ----------


async def test_create_persists_and_get_returns_same_row(
    repo: SqlAlchemyTaskRepository, seeded: dict
) -> None:
    created = await repo.create(
        _task_entity(workspace_id=seeded["workspace_id"], creator_id=seeded["creator_id"])
    )
    fetched = await repo.get_by_id(created.id)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.title == "demo"
    assert fetched.status is TaskStatus.PENDING


async def test_get_by_id_returns_none_for_unknown(repo: SqlAlchemyTaskRepository) -> None:
    assert await repo.get_by_id(uuid4()) is None


async def test_list_by_ids_empty_short_circuits(repo: SqlAlchemyTaskRepository) -> None:
    assert await repo.list_by_ids([]) == []


async def test_list_by_ids_returns_requested(repo: SqlAlchemyTaskRepository, seeded: dict) -> None:
    a = await repo.create(
        _task_entity(
            workspace_id=seeded["workspace_id"], creator_id=seeded["creator_id"], title="a"
        )
    )
    b = await repo.create(
        _task_entity(
            workspace_id=seeded["workspace_id"],
            creator_id=seeded["creator_id"],
            title="b",
            seq=2,
        )
    )
    fetched = await repo.list_by_ids([a.id, b.id])
    titles = {t.title for t in fetched}
    assert titles == {"a", "b"}


# ---------- assign + update_priority ----------


async def test_assign_sets_assignee(repo: SqlAlchemyTaskRepository, seeded: dict) -> None:
    t = await repo.create(
        _task_entity(workspace_id=seeded["workspace_id"], creator_id=seeded["creator_id"])
    )
    updated = await repo.assign(t.id, seeded["assignee_id"])
    assert updated.assignee_id == seeded["assignee_id"]


async def test_assign_unknown_raises(repo: SqlAlchemyTaskRepository, seeded: dict) -> None:
    with pytest.raises(TaskNotFoundError):
        await repo.assign(uuid4(), seeded["assignee_id"])


async def test_update_priority(repo: SqlAlchemyTaskRepository, seeded: dict) -> None:
    t = await repo.create(
        _task_entity(workspace_id=seeded["workspace_id"], creator_id=seeded["creator_id"])
    )
    updated = await repo.update_priority(t.id, 9)
    assert updated.priority == 9


async def test_update_priority_unknown_raises(repo: SqlAlchemyTaskRepository) -> None:
    with pytest.raises(TaskNotFoundError):
        await repo.update_priority(uuid4(), 1)


# ---------- update_status ----------


async def test_update_status_to_done_stamps_completed_at(
    repo: SqlAlchemyTaskRepository, seeded: dict
) -> None:
    t = await repo.create(
        _task_entity(workspace_id=seeded["workspace_id"], creator_id=seeded["creator_id"])
    )
    updated = await repo.update_status(t.id, status=TaskStatus.DONE, tokens_used=42)
    assert updated.status is TaskStatus.DONE
    assert updated.completed_at is not None
    assert updated.tokens_used == 42


async def test_update_status_back_to_in_progress_clears_completed_at(
    repo: SqlAlchemyTaskRepository, seeded: dict
) -> None:
    """Reopening a DONE task clears completed_at — the field is the
    "first time we landed in DONE", reset on the rare reopen."""
    t = await repo.create(
        _task_entity(workspace_id=seeded["workspace_id"], creator_id=seeded["creator_id"])
    )
    await repo.update_status(t.id, status=TaskStatus.DONE)
    reopened = await repo.update_status(t.id, status=TaskStatus.IN_PROGRESS)
    assert reopened.completed_at is None


async def test_update_status_unknown_raises(repo: SqlAlchemyTaskRepository) -> None:
    with pytest.raises(TaskNotFoundError):
        await repo.update_status(uuid4(), status=TaskStatus.DONE)


# ---------- list_by_workspace + filters ----------


async def test_list_by_workspace_returns_all_when_unfiltered(
    repo: SqlAlchemyTaskRepository, seeded: dict
) -> None:
    await repo.create(
        _task_entity(
            workspace_id=seeded["workspace_id"], creator_id=seeded["creator_id"], title="a"
        )
    )
    await repo.create(
        _task_entity(
            workspace_id=seeded["workspace_id"],
            creator_id=seeded["creator_id"],
            title="b",
            seq=2,
        )
    )
    rows = await repo.list_by_workspace(seeded["workspace_id"])
    assert len(rows) == 2


async def test_list_by_workspace_status_filter(
    repo: SqlAlchemyTaskRepository, seeded: dict
) -> None:
    await repo.create(
        _task_entity(
            workspace_id=seeded["workspace_id"],
            creator_id=seeded["creator_id"],
            status=TaskStatus.PENDING,
        )
    )
    done = await repo.create(
        _task_entity(
            workspace_id=seeded["workspace_id"],
            creator_id=seeded["creator_id"],
            status=TaskStatus.DONE,
            seq=2,
        )
    )
    rows = await repo.list_by_workspace(seeded["workspace_id"], status=TaskStatus.DONE)
    assert len(rows) == 1
    assert rows[0].id == done.id


async def test_list_by_workspace_blocked_only(repo: SqlAlchemyTaskRepository, seeded: dict) -> None:
    await repo.create(
        _task_entity(workspace_id=seeded["workspace_id"], creator_id=seeded["creator_id"])
    )
    blocked = await repo.create(
        _task_entity(
            workspace_id=seeded["workspace_id"],
            creator_id=seeded["creator_id"],
            seq=2,
            is_blocked=True,
            blocked_reason="waiting on data",
        )
    )
    rows = await repo.list_by_workspace(seeded["workspace_id"], blocked_only=True)
    assert len(rows) == 1
    assert rows[0].id == blocked.id


async def test_list_by_workspace_filters_by_project_team_assignee_priority(
    repo: SqlAlchemyTaskRepository, seeded: dict
) -> None:
    """Verify every filter clause shapes the result correctly."""
    target = await repo.create(
        _task_entity(
            workspace_id=seeded["workspace_id"],
            creator_id=seeded["creator_id"],
            project_id=seeded["project_id"],
            team_id=seeded["team_a_id"],
            assignee_id=seeded["assignee_id"],
            priority=5,
        )
    )
    # Decoy: same workspace but no project/team/assignee.
    await repo.create(
        _task_entity(
            workspace_id=seeded["workspace_id"],
            creator_id=seeded["creator_id"],
            seq=2,
            priority=10,
        )
    )

    by_project = await repo.list_by_workspace(
        seeded["workspace_id"], project_id=seeded["project_id"]
    )
    assert {t.id for t in by_project} == {target.id}

    by_team = await repo.list_by_workspace(seeded["workspace_id"], team_id=seeded["team_a_id"])
    assert {t.id for t in by_team} == {target.id}

    by_assignee = await repo.list_by_workspace(
        seeded["workspace_id"], assignee_id=seeded["assignee_id"]
    )
    assert {t.id for t in by_assignee} == {target.id}

    bounded = await repo.list_by_workspace(seeded["workspace_id"], priority_min=1, priority_max=6)
    assert {t.id for t in bounded} == {target.id}


# ---------- list_for_dashboard ----------


async def test_list_for_dashboard_admin_path_returns_all(
    repo: SqlAlchemyTaskRepository, seeded: dict
) -> None:
    """No member_id, team_id or project_ids → admin path → workspace-wide."""
    a = await repo.create(
        _task_entity(
            workspace_id=seeded["workspace_id"], creator_id=seeded["creator_id"], title="a"
        )
    )
    b = await repo.create(
        _task_entity(
            workspace_id=seeded["workspace_id"],
            creator_id=seeded["creator_id"],
            title="b",
            seq=2,
        )
    )
    rows = await repo.list_for_dashboard(seeded["workspace_id"])
    ids = {t.id for t in rows}
    assert ids == {a.id, b.id}


async def test_list_for_dashboard_member_or_team_or_project(
    repo: SqlAlchemyTaskRepository, seeded: dict
) -> None:
    """The OR-of-clauses path: any matching condition pulls the task in."""
    by_member = await repo.create(
        _task_entity(
            workspace_id=seeded["workspace_id"],
            creator_id=seeded["creator_id"],
            assignee_id=seeded["assignee_id"],
        )
    )
    by_team = await repo.create(
        _task_entity(
            workspace_id=seeded["workspace_id"],
            creator_id=seeded["creator_id"],
            team_id=seeded["team_a_id"],
            seq=2,
        )
    )
    by_project = await repo.create(
        _task_entity(
            workspace_id=seeded["workspace_id"],
            creator_id=seeded["creator_id"],
            project_id=seeded["project_id"],
            seq=3,
        )
    )
    # Decoy with no overlapping field — should NOT appear.
    await repo.create(
        _task_entity(
            workspace_id=seeded["workspace_id"],
            creator_id=seeded["creator_id"],
            seq=4,
        )
    )

    rows = await repo.list_for_dashboard(
        seeded["workspace_id"],
        member_id=seeded["assignee_id"],
        team_id=seeded["team_a_id"],
        project_ids=[seeded["project_id"]],
    )
    assert {t.id for t in rows} == {by_member.id, by_team.id, by_project.id}


async def test_list_for_dashboard_empty_project_ids_treated_as_no_filter(
    repo: SqlAlchemyTaskRepository, seeded: dict
) -> None:
    """The repo treats ``project_ids=[]`` as "no project filter" rather
    than "match nothing". Verifying the docstring contract."""
    a = await repo.create(
        _task_entity(workspace_id=seeded["workspace_id"], creator_id=seeded["creator_id"])
    )
    rows = await repo.list_for_dashboard(seeded["workspace_id"], project_ids=[])
    assert {t.id for t in rows} == {a.id}


# ---------- list_project_ids_for_team ----------


async def test_list_project_ids_for_team_returns_distinct(
    repo: SqlAlchemyTaskRepository, seeded: dict
) -> None:
    """Two tasks on the same project + same team should produce one row."""
    await repo.create(
        _task_entity(
            workspace_id=seeded["workspace_id"],
            creator_id=seeded["creator_id"],
            team_id=seeded["team_a_id"],
            project_id=seeded["project_id"],
        )
    )
    await repo.create(
        _task_entity(
            workspace_id=seeded["workspace_id"],
            creator_id=seeded["creator_id"],
            team_id=seeded["team_a_id"],
            project_id=seeded["project_id"],
            seq=2,
        )
    )
    # Different team — should NOT contribute.
    await repo.create(
        _task_entity(
            workspace_id=seeded["workspace_id"],
            creator_id=seeded["creator_id"],
            team_id=seeded["team_b_id"],
            project_id=seeded["project_id"],
            seq=3,
        )
    )
    ids = await repo.list_project_ids_for_team(seeded["workspace_id"], seeded["team_a_id"])
    assert ids == [seeded["project_id"]]


# ---------- set_blocked + update_links ----------


async def test_set_blocked_then_unblock_clears_reason(
    repo: SqlAlchemyTaskRepository, seeded: dict
) -> None:
    t = await repo.create(
        _task_entity(workspace_id=seeded["workspace_id"], creator_id=seeded["creator_id"])
    )
    blocked = await repo.set_blocked(t.id, is_blocked=True, blocked_reason="waiting on prod data")
    assert blocked.is_blocked is True
    assert blocked.blocked_reason == "waiting on prod data"

    unblocked = await repo.set_blocked(t.id, is_blocked=False, blocked_reason=None)
    assert unblocked.is_blocked is False
    assert unblocked.blocked_reason is None


async def test_set_blocked_unknown_raises(repo: SqlAlchemyTaskRepository) -> None:
    with pytest.raises(TaskNotFoundError):
        await repo.set_blocked(uuid4(), is_blocked=True, blocked_reason="x")


async def test_update_links_assigns_then_clears(
    repo: SqlAlchemyTaskRepository, seeded: dict
) -> None:
    t = await repo.create(
        _task_entity(workspace_id=seeded["workspace_id"], creator_id=seeded["creator_id"])
    )
    # Assign project + team.
    assigned = await repo.update_links(
        t.id, project_id=seeded["project_id"], team_id=seeded["team_a_id"]
    )
    assert assigned.project_id == seeded["project_id"]
    assert assigned.team_id == seeded["team_a_id"]

    # Clear both via the explicit flag.
    cleared = await repo.update_links(
        t.id,
        project_id=None,
        team_id=None,
        clear_project=True,
        clear_team=True,
    )
    assert cleared.project_id is None
    assert cleared.team_id is None


async def test_update_links_unknown_raises(repo: SqlAlchemyTaskRepository) -> None:
    with pytest.raises(TaskNotFoundError):
        await repo.update_links(uuid4(), project_id=None, team_id=None)
