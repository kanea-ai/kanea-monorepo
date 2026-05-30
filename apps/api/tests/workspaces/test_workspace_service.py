"""Unit tests for WorkspaceService.rename.

Contract:
- Only the WORKSPACE_OWNER of the target workspace can rename it.
- The path workspace_id must match the principal's JWT workspace_id;
  cross-tenant attempts surface as WorkspaceNotFoundError (404 at the
  route) so existence isn't leaked.
- ``workspaces.name`` is globally unique. On conflict the service
  raises WorkspaceNameConflictError (mapped to 409).
- A successful rename regenerates the slug from the new name (slug
  comes from ``_generate_slug`` which appends a random hex suffix so
  collisions on the slug column are essentially impossible).
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.application.tasks.schemas import Principal
from app.application.workspaces.schemas import RenameWorkspaceRequest
from app.application.workspaces.service import WorkspaceService
from app.domain.entities import Workspace
from app.domain.enums import MemberRole, MemberType
from app.domain.exceptions import (
    ForbiddenError,
    WorkspaceNameConflictError,
    WorkspaceNotFoundError,
)


def _principal(
    *,
    role: MemberRole = MemberRole.WORKSPACE_OWNER,
    workspace_id=None,
) -> Principal:
    return Principal(
        member_id=uuid4(),
        workspace_id=workspace_id or uuid4(),
        type=MemberType.HUMAN,
        priority=1,
        scope="human",
        role=role,
    )


def _workspace(workspace_id=None, *, name: str = "Acme") -> Workspace:
    now = datetime.now(UTC)
    return Workspace(
        id=workspace_id or uuid4(),
        name=name,
        slug=f"{name.lower()}-abc123",
        task_prefix="ACME",
        next_task_seq=1,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(repo: AsyncMock) -> WorkspaceService:
    return WorkspaceService(workspaces=repo)


async def test_owner_can_rename(service: WorkspaceService, repo: AsyncMock) -> None:
    p = _principal(role=MemberRole.WORKSPACE_OWNER)
    repo.get_by_id.return_value = _workspace(p.workspace_id, name="Old")
    repo.rename.side_effect = lambda ws_id, *, name, slug: _workspace(ws_id, name=name)

    result = await service.rename(p.workspace_id, RenameWorkspaceRequest(name="New"), p)

    assert result.name == "New"
    repo.rename.assert_awaited_once()
    call = repo.rename.await_args
    # Slug is regenerated from the new name. We don't assert the
    # exact value (random suffix) — just that the service didn't
    # forward the old one verbatim.
    assert call.args[0] == p.workspace_id
    assert call.kwargs["name"] == "New"
    assert call.kwargs["slug"].startswith("new-")


async def test_admin_role_cannot_rename(service: WorkspaceService, repo: AsyncMock) -> None:
    p = _principal(role=MemberRole.WORKSPACE_ADMIN)
    repo.get_by_id.return_value = _workspace(p.workspace_id, name="Old")
    with pytest.raises(ForbiddenError):
        await service.rename(p.workspace_id, RenameWorkspaceRequest(name="New"), p)
    repo.rename.assert_not_called()


async def test_user_role_cannot_rename(service: WorkspaceService, repo: AsyncMock) -> None:
    p = _principal(role=MemberRole.WORKSPACE_USER)
    repo.get_by_id.return_value = _workspace(p.workspace_id, name="Old")
    with pytest.raises(ForbiddenError):
        await service.rename(p.workspace_id, RenameWorkspaceRequest(name="New"), p)
    repo.rename.assert_not_called()


async def test_cross_workspace_path_404s(service: WorkspaceService, repo: AsyncMock) -> None:
    """The path workspace_id must match the principal's JWT
    workspace_id; otherwise the call surfaces as not-found rather than
    forbidden, so existence of OTHER workspaces isn't leaked."""
    p = _principal(role=MemberRole.WORKSPACE_OWNER)
    other_id = uuid4()
    with pytest.raises(WorkspaceNotFoundError):
        await service.rename(other_id, RenameWorkspaceRequest(name="X"), p)
    repo.get_by_id.assert_not_called()
    repo.rename.assert_not_called()


async def test_missing_workspace_404s(service: WorkspaceService, repo: AsyncMock) -> None:
    """JWT points at a workspace_id whose row no longer exists (e.g.
    deleted after the JWT was minted). Service surfaces 404 so the
    caller can re-authenticate."""
    p = _principal(role=MemberRole.WORKSPACE_OWNER)
    repo.get_by_id.return_value = None
    with pytest.raises(WorkspaceNotFoundError):
        await service.rename(p.workspace_id, RenameWorkspaceRequest(name="X"), p)


async def test_name_conflict_raises(service: WorkspaceService, repo: AsyncMock) -> None:
    """Globally-unique workspaces.name: a name already in use anywhere
    on the platform surfaces as WorkspaceNameConflictError (mapped to
    409)."""
    p = _principal(role=MemberRole.WORKSPACE_OWNER)
    repo.get_by_id.return_value = _workspace(p.workspace_id, name="Old")
    repo.rename.side_effect = IntegrityError("unique", params=None, orig=Exception())
    with pytest.raises(WorkspaceNameConflictError):
        await service.rename(p.workspace_id, RenameWorkspaceRequest(name="Taken"), p)


async def test_unchanged_name_is_noop(service: WorkspaceService, repo: AsyncMock) -> None:
    """Renaming to the current name is a no-op — no repo write, no
    error. Keeps the audit trail tidy and avoids a spurious
    IntegrityError when the row is its own slug owner."""
    p = _principal(role=MemberRole.WORKSPACE_OWNER)
    current = _workspace(p.workspace_id, name="Same")
    repo.get_by_id.return_value = current
    result = await service.rename(p.workspace_id, RenameWorkspaceRequest(name="Same"), p)
    assert result.name == "Same"
    repo.rename.assert_not_called()
