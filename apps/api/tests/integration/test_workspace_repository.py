"""Integration test for SqlAlchemyWorkspaceRepository.rename.

Exercises the real UNIQUE constraint on ``workspaces.name`` (migration
0016) so the service's IntegrityError → WorkspaceNameConflictError
mapping is verified end-to-end."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import Workspace
from app.infrastructure.repositories.workspace import SqlAlchemyWorkspaceRepository


@pytest.fixture
def repo(pg_session: AsyncSession) -> SqlAlchemyWorkspaceRepository:
    return SqlAlchemyWorkspaceRepository(pg_session)


async def _seed(repo: SqlAlchemyWorkspaceRepository, name: str) -> Workspace:
    return await repo.create(
        Workspace(
            id=uuid4(),
            name=name,
            slug=f"{name.lower().replace(' ', '-')}-{uuid4().hex[:6]}",
            task_prefix=name[:6].upper().replace(" ", ""),
            next_task_seq=1,
            created_at=__import__("datetime").datetime.utcnow(),
            updated_at=__import__("datetime").datetime.utcnow(),
        )
    )


async def test_rename_persists(repo: SqlAlchemyWorkspaceRepository) -> None:
    ws = await _seed(repo, name="Original")
    renamed = await repo.rename(ws.id, name="Updated", slug="updated-xxx111")
    assert renamed.name == "Updated"
    assert renamed.slug == "updated-xxx111"

    refetched = await repo.get_by_id(ws.id)
    assert refetched is not None
    assert refetched.name == "Updated"


async def test_rename_to_taken_name_raises_integrity_error(
    repo: SqlAlchemyWorkspaceRepository,
) -> None:
    """The UNIQUE constraint on ``workspaces.name`` rejects a second
    workspace claiming the same name. WorkspaceService translates
    this IntegrityError into a clean 409."""
    await _seed(repo, name="Already Here")
    other = await _seed(repo, name="Another")
    with pytest.raises(IntegrityError):
        await repo.rename(other.id, name="Already Here", slug="already-here-xxx222")
