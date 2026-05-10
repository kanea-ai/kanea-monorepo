"""Tests for ProjectService.

Contract:
- Projects are workspace-scoped. Cross-tenant ids 404.
- Listing hides ARCHIVED by default; ?include_archived=true reveals.
- Create / update name conflict (unique constraint per workspace) maps
  to ProjectNameConflictError -> 409.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.application.projects.schemas import (
    CreateProjectRequest,
    UpdateProjectRequest,
)
from app.application.projects.service import ProjectService
from app.domain.entities import Project
from app.domain.enums import ProjectStatus
from app.domain.exceptions import ProjectNameConflictError, ProjectNotFoundError
from tests.tasks.factories import make_principal


def _project(
    *,
    workspace_id=None,
    name="Launch website",
    status=ProjectStatus.ACTIVE,
) -> Project:
    now = datetime.now(UTC)
    return Project(
        id=uuid4(),
        workspace_id=workspace_id or uuid4(),
        name=name,
        description=None,
        status=status,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def projects_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(projects_repo: AsyncMock) -> ProjectService:
    return ProjectService(projects=projects_repo)


# ---------- list ----------


async def test_list_passes_include_archived(
    service: ProjectService, projects_repo: AsyncMock
) -> None:
    p = make_principal()
    projects_repo.list_for_workspace.return_value = ([], 0)
    await service.list_for_workspace(p, include_archived=True)
    projects_repo.list_for_workspace.assert_awaited_once_with(
        p.workspace_id, include_archived=True, skip=0, limit=None
    )


async def test_list_paginates(service: ProjectService, projects_repo: AsyncMock) -> None:
    """skip / limit forward to the repo and the response carries the
    repo's total count untouched."""
    p = make_principal()
    projects_repo.list_for_workspace.return_value = ([], 12)
    page = await service.list_for_workspace(p, skip=4, limit=2)
    assert page.total == 12
    projects_repo.list_for_workspace.assert_awaited_once_with(
        p.workspace_id, include_archived=False, skip=4, limit=2
    )


# ---------- get_by_id (tenant isolation) ----------


async def test_get_by_id_404s_for_other_workspace(
    service: ProjectService, projects_repo: AsyncMock
) -> None:
    p = make_principal()
    projects_repo.get_by_id.return_value = _project(workspace_id=uuid4())  # other ws
    with pytest.raises(ProjectNotFoundError):
        await service.get_by_id(uuid4(), p)


async def test_get_by_id_404s_when_missing(
    service: ProjectService, projects_repo: AsyncMock
) -> None:
    p = make_principal()
    projects_repo.get_by_id.return_value = None
    with pytest.raises(ProjectNotFoundError):
        await service.get_by_id(uuid4(), p)


# ---------- create ----------


async def test_create_persists_active_project(
    service: ProjectService, projects_repo: AsyncMock
) -> None:
    p = make_principal()
    projects_repo.create.side_effect = lambda proj: proj

    response = await service.create(
        CreateProjectRequest(name="Launch website", description="Q3 push"), p
    )

    projects_repo.create.assert_awaited_once()
    persisted = projects_repo.create.await_args.args[0]
    assert persisted.workspace_id == p.workspace_id
    assert persisted.status is ProjectStatus.ACTIVE
    assert persisted.name == "Launch website"
    assert response.name == "Launch website"


async def test_create_name_conflict_surfaces_409_signal(
    service: ProjectService, projects_repo: AsyncMock
) -> None:
    p = make_principal()
    projects_repo.create.side_effect = IntegrityError("statement", {}, Exception())
    with pytest.raises(ProjectNameConflictError):
        await service.create(CreateProjectRequest(name="Dup"), p)


# ---------- update ----------


async def test_update_clears_description_when_explicitly_null(
    service: ProjectService, projects_repo: AsyncMock
) -> None:
    """Setting description=null clears it; omitting the field leaves
    it untouched. Pydantic represents both as None — model_fields_set
    disambiguates."""
    p = make_principal()
    existing = _project(workspace_id=p.workspace_id)
    projects_repo.get_by_id.return_value = existing
    projects_repo.update.side_effect = lambda *a, **kw: existing

    request = UpdateProjectRequest.model_validate({"description": None})
    await service.update(existing.id, request, p)

    projects_repo.update.assert_awaited_once()
    _, kwargs = projects_repo.update.await_args
    assert kwargs["clear_description"] is True


async def test_update_404s_for_other_workspace(
    service: ProjectService, projects_repo: AsyncMock
) -> None:
    p = make_principal()
    projects_repo.get_by_id.return_value = _project(workspace_id=uuid4())
    with pytest.raises(ProjectNotFoundError):
        await service.update(uuid4(), UpdateProjectRequest(name="Renamed"), p)


# ---------- delete ----------


async def test_delete_404s_for_other_workspace(
    service: ProjectService, projects_repo: AsyncMock
) -> None:
    p = make_principal()
    projects_repo.get_by_id.return_value = _project(workspace_id=uuid4())
    with pytest.raises(ProjectNotFoundError):
        await service.delete(uuid4(), p)
    projects_repo.delete.assert_not_called()
