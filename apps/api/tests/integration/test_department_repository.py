"""Integration tests for SqlAlchemyDepartmentRepository.

Focused on the migration-0022 additions:

  * ``departments.head_id`` persists and round-trips through the repo.
  * ``ON DELETE SET NULL`` on the FK clears the head_id when the
    member row is deleted — the Department row survives.
  * ``TeamRepository.get_department_head_for_team`` walks team →
    department → head_id in one query.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import Department
from app.domain.enums import MemberRole, MemberType
from app.infrastructure.db.models import (
    MemberModel,
    TeamModel,
    UserModel,
    WorkspaceModel,
)
from app.infrastructure.repositories.department import SqlAlchemyDepartmentRepository
from app.infrastructure.repositories.team import SqlAlchemyTeamRepository


@pytest.fixture
def dept_repo(pg_session: AsyncSession) -> SqlAlchemyDepartmentRepository:
    return SqlAlchemyDepartmentRepository(pg_session)


@pytest.fixture
def team_repo(pg_session: AsyncSession) -> SqlAlchemyTeamRepository:
    return SqlAlchemyTeamRepository(pg_session)


async def _seed_workspace_and_member(pg_session: AsyncSession) -> tuple[UUID, UUID]:
    workspace = WorkspaceModel(
        id=uuid4(),
        name=f"WS-{uuid4().hex[:6]}",
        slug=f"ws-{uuid4().hex[:6]}",
        task_prefix="TST",
        next_task_seq=1,
    )
    pg_session.add(workspace)
    await pg_session.flush()

    user = UserModel(
        id=uuid4(),
        email=f"head-{uuid4().hex[:6]}@example.com",
        full_name="Head",
        password_hash="bcrypt$placeholder",  # pragma: allowlist secret
    )
    pg_session.add(user)
    await pg_session.flush()

    head = MemberModel(
        id=uuid4(),
        workspace_id=workspace.id,
        user_id=user.id,
        type=MemberType.HUMAN,
        name="Head",
        email=user.email,
        priority=2,
        role=MemberRole.WORKSPACE_ADMIN,
    )
    pg_session.add(head)
    await pg_session.flush()
    return workspace.id, head.id


async def test_create_with_head_id_persists(
    dept_repo: SqlAlchemyDepartmentRepository, pg_session: AsyncSession
) -> None:
    workspace_id, head_id = await _seed_workspace_and_member(pg_session)
    dept = await dept_repo.create(
        Department(
            id=uuid4(),
            workspace_id=workspace_id,
            name="Engineering",
            description=None,
            head_id=head_id,
        )
    )
    assert dept.head_id == head_id

    refetched = await dept_repo.get_by_id(dept.id)
    assert refetched is not None
    assert refetched.head_id == head_id


async def test_update_can_clear_head(
    dept_repo: SqlAlchemyDepartmentRepository, pg_session: AsyncSession
) -> None:
    workspace_id, head_id = await _seed_workspace_and_member(pg_session)
    dept = await dept_repo.create(
        Department(
            id=uuid4(),
            workspace_id=workspace_id,
            name="Engineering",
            description=None,
            head_id=head_id,
        )
    )
    cleared = await dept_repo.update(dept.id, clear_head=True)
    assert cleared.head_id is None


async def test_head_set_null_on_member_delete(
    dept_repo: SqlAlchemyDepartmentRepository, pg_session: AsyncSession
) -> None:
    """FK is ON DELETE SET NULL — removing the head member clears
    departments.head_id but the Department row survives."""
    workspace_id, head_id = await _seed_workspace_and_member(pg_session)
    dept = await dept_repo.create(
        Department(
            id=uuid4(),
            workspace_id=workspace_id,
            name="Engineering",
            description=None,
            head_id=head_id,
        )
    )

    member = await pg_session.get(MemberModel, head_id)
    assert member is not None
    await pg_session.delete(member)
    await pg_session.flush()

    refreshed = await dept_repo.get_by_id(dept.id)
    assert refreshed is not None
    assert refreshed.head_id is None


async def test_get_department_head_for_team(
    team_repo: SqlAlchemyTeamRepository,
    dept_repo: SqlAlchemyDepartmentRepository,
    pg_session: AsyncSession,
) -> None:
    workspace_id, head_id = await _seed_workspace_and_member(pg_session)
    dept = await dept_repo.create(
        Department(
            id=uuid4(),
            workspace_id=workspace_id,
            name="Engineering",
            description=None,
            head_id=head_id,
        )
    )
    team = TeamModel(
        id=uuid4(),
        workspace_id=workspace_id,
        name="Backend",
        department_id=dept.id,
    )
    pg_session.add(team)
    await pg_session.flush()

    fetched = await team_repo.get_department_head_for_team(team.id)
    assert fetched == head_id

    # Detached team (no department) returns None.
    floating = TeamModel(
        id=uuid4(),
        workspace_id=workspace_id,
        name="Floating",
        department_id=None,
    )
    pg_session.add(floating)
    await pg_session.flush()
    assert await team_repo.get_department_head_for_team(floating.id) is None


async def test_unique_head_id_partial_index_rejects_second_head(
    dept_repo: SqlAlchemyDepartmentRepository, pg_session: AsyncSession
) -> None:
    """DB-level safety net: even if the service-layer pre-flight is
    bypassed (concurrent inserts, direct SQL, …), the partial unique
    index forbids one member from heading two departments."""
    from sqlalchemy.exc import IntegrityError

    workspace_id, head_id = await _seed_workspace_and_member(pg_session)
    await dept_repo.create(
        Department(
            id=uuid4(),
            workspace_id=workspace_id,
            name="Engineering",
            description=None,
            head_id=head_id,
        )
    )
    with pytest.raises(IntegrityError):
        await dept_repo.create(
            Department(
                id=uuid4(),
                workspace_id=workspace_id,
                name="Operations",
                description=None,
                head_id=head_id,
            )
        )


async def test_unique_head_id_partial_index_allows_multiple_nulls(
    dept_repo: SqlAlchemyDepartmentRepository, pg_session: AsyncSession
) -> None:
    """The unique index is partial (``WHERE head_id IS NOT NULL``), so
    multiple departments without a head coexist fine."""
    workspace_id, _ = await _seed_workspace_and_member(pg_session)
    await dept_repo.create(
        Department(
            id=uuid4(),
            workspace_id=workspace_id,
            name="No Head A",
            description=None,
            head_id=None,
        )
    )
    await dept_repo.create(
        Department(
            id=uuid4(),
            workspace_id=workspace_id,
            name="No Head B",
            description=None,
            head_id=None,
        )
    )


async def test_get_for_head_returns_the_one_department(
    dept_repo: SqlAlchemyDepartmentRepository, pg_session: AsyncSession
) -> None:
    workspace_id, head_id = await _seed_workspace_and_member(pg_session)
    dept = await dept_repo.create(
        Department(
            id=uuid4(),
            workspace_id=workspace_id,
            name="Engineering",
            description=None,
            head_id=head_id,
        )
    )
    fetched = await dept_repo.get_for_head(head_id)
    assert fetched is not None
    assert fetched.id == dept.id

    # Headless lookup returns None.
    assert await dept_repo.get_for_head(uuid4()) is None


async def test_list_team_ids_for_department_head(
    team_repo: SqlAlchemyTeamRepository,
    dept_repo: SqlAlchemyDepartmentRepository,
    pg_session: AsyncSession,
) -> None:
    workspace_id, head_id = await _seed_workspace_and_member(pg_session)
    dept = await dept_repo.create(
        Department(
            id=uuid4(),
            workspace_id=workspace_id,
            name="Engineering",
            description=None,
            head_id=head_id,
        )
    )
    # Two teams under the headed department.
    team_a = TeamModel(id=uuid4(), workspace_id=workspace_id, name="A", department_id=dept.id)
    team_b = TeamModel(id=uuid4(), workspace_id=workspace_id, name="B", department_id=dept.id)
    # One team in a different department that this member does NOT head.
    other_dept = await dept_repo.create(
        Department(
            id=uuid4(),
            workspace_id=workspace_id,
            name="Other",
            description=None,
            head_id=None,
        )
    )
    team_c = TeamModel(id=uuid4(), workspace_id=workspace_id, name="C", department_id=other_dept.id)
    pg_session.add_all([team_a, team_b, team_c])
    await pg_session.flush()

    ids = await team_repo.list_team_ids_for_department_head(head_id)
    assert set(ids) == {team_a.id, team_b.id}
