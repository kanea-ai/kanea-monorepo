"""Tests for the new Team metadata: description + department_id.

Contract:
- A team can be created with a description and a department_id.
- A passed department_id from a different workspace is rejected as
  DepartmentNotFoundError (404 at the route).
- The list endpoint accepts an optional ``department_id`` filter that
  is forwarded to the repo.
- PATCH supports partial updates AND explicit clears (description=null,
  department_id=null) without touching omitted fields.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.application.tasks.schemas import Principal
from app.application.teams.schemas import CreateTeamRequest, UpdateTeamRequest
from app.application.teams.service import TeamService
from app.domain.entities import Department, Team
from app.domain.enums import MemberRole, MemberType
from app.domain.exceptions import DepartmentNotFoundError


def _principal(workspace_id=None) -> Principal:
    return Principal(
        member_id=uuid4(),
        workspace_id=workspace_id or uuid4(),
        type=MemberType.HUMAN,
        priority=1,
        scope="human",
        role=MemberRole.WORKSPACE_OWNER,
    )


def _team(workspace_id, *, department_id=None, description=None) -> Team:
    now = datetime.now(UTC)
    return Team(
        id=uuid4(),
        workspace_id=workspace_id,
        name="Backend",
        description=description,
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
def teams_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def departments_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(teams_repo: AsyncMock, departments_repo: AsyncMock) -> TeamService:
    return TeamService(teams=teams_repo, departments=departments_repo)


# ---------- list with department filter ----------


async def test_list_forwards_department_filter(service: TeamService, teams_repo: AsyncMock) -> None:
    p = _principal()
    teams_repo.list_for_workspace.return_value = []
    dept_id = uuid4()
    await service.list_for_workspace(p, department_id=dept_id)
    teams_repo.list_for_workspace.assert_awaited_once_with(p.workspace_id, department_id=dept_id)


async def test_list_default_passes_none(service: TeamService, teams_repo: AsyncMock) -> None:
    p = _principal()
    teams_repo.list_for_workspace.return_value = []
    await service.list_for_workspace(p)
    teams_repo.list_for_workspace.assert_awaited_once_with(p.workspace_id, department_id=None)


# ---------- create with description / department ----------


async def test_create_with_description_and_department(
    service: TeamService, teams_repo: AsyncMock, departments_repo: AsyncMock
) -> None:
    p = _principal()
    dept = _dept(p.workspace_id)
    departments_repo.get_by_id.return_value = dept
    teams_repo.create.return_value = _team(p.workspace_id)

    await service.create(
        CreateTeamRequest(name="Backend", description="Owns the API.", department_id=dept.id),
        p,
    )
    departments_repo.get_by_id.assert_awaited_once_with(dept.id)
    teams_repo.create.assert_awaited_once()
    created_team = teams_repo.create.call_args[0][0]
    assert created_team.description == "Owns the API."
    assert created_team.department_id == dept.id


async def test_create_rejects_cross_tenant_department(
    service: TeamService, departments_repo: AsyncMock, teams_repo: AsyncMock
) -> None:
    p = _principal()
    departments_repo.get_by_id.return_value = _dept(uuid4())  # other workspace
    with pytest.raises(DepartmentNotFoundError):
        await service.create(CreateTeamRequest(name="Backend", department_id=uuid4()), p)
    teams_repo.create.assert_not_called()


async def test_create_without_department_does_not_lookup(
    service: TeamService, teams_repo: AsyncMock, departments_repo: AsyncMock
) -> None:
    p = _principal()
    teams_repo.create.return_value = _team(p.workspace_id)
    await service.create(CreateTeamRequest(name="Backend"), p)
    departments_repo.get_by_id.assert_not_called()


# ---------- update: partial + explicit clears ----------


async def test_update_clears_description_explicitly(
    service: TeamService, teams_repo: AsyncMock
) -> None:
    p = _principal()
    target = _team(p.workspace_id, description="old")
    teams_repo.get_by_id.return_value = target
    teams_repo.update.return_value = target

    await service.update(
        target.id,
        UpdateTeamRequest.model_validate({"description": None}),
        p,
    )
    teams_repo.update.assert_awaited_once_with(
        target.id,
        name=None,
        description=None,
        department_id=None,
        clear_description=True,
        clear_department=False,
    )


async def test_update_clears_department_explicitly(
    service: TeamService, teams_repo: AsyncMock
) -> None:
    p = _principal()
    target = _team(p.workspace_id)
    teams_repo.get_by_id.return_value = target
    teams_repo.update.return_value = target

    await service.update(
        target.id,
        UpdateTeamRequest.model_validate({"department_id": None}),
        p,
    )
    teams_repo.update.assert_awaited_once_with(
        target.id,
        name=None,
        description=None,
        department_id=None,
        clear_description=False,
        clear_department=True,
    )


async def test_update_omits_fields_not_in_payload(
    service: TeamService, teams_repo: AsyncMock
) -> None:
    p = _principal()
    target = _team(p.workspace_id, description="kept")
    teams_repo.get_by_id.return_value = target
    teams_repo.update.return_value = target

    # Payload only renames the team — description and department must
    # NOT be reset.
    await service.update(target.id, UpdateTeamRequest(name="Backend2"), p)
    teams_repo.update.assert_awaited_once_with(
        target.id,
        name="Backend2",
        description=None,
        department_id=None,
        clear_description=False,
        clear_department=False,
    )


async def test_update_rejects_cross_tenant_department(
    service: TeamService,
    teams_repo: AsyncMock,
    departments_repo: AsyncMock,
) -> None:
    p = _principal()
    target = _team(p.workspace_id)
    teams_repo.get_by_id.return_value = target
    departments_repo.get_by_id.return_value = _dept(uuid4())  # other workspace
    with pytest.raises(DepartmentNotFoundError):
        await service.update(target.id, UpdateTeamRequest(department_id=uuid4()), p)
    teams_repo.update.assert_not_called()
