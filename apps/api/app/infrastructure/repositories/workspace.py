from __future__ import annotations

from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import Workspace
from app.infrastructure.db.models import WorkspaceModel


def _to_entity(row: WorkspaceModel) -> Workspace:
    return Workspace(
        id=row.id,
        name=row.name,
        slug=row.slug,
        task_prefix=row.task_prefix,
        next_task_seq=row.next_task_seq,
        suspended_at=row.suspended_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlAlchemyWorkspaceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, workspace_id):  # type: ignore[no-untyped-def]
        row = await self._session.get(WorkspaceModel, workspace_id)
        return _to_entity(row) if row is not None else None

    async def create(self, workspace: Workspace) -> Workspace:
        row = WorkspaceModel(
            id=workspace.id,
            name=workspace.name,
            slug=workspace.slug,
            task_prefix=workspace.task_prefix,
            next_task_seq=workspace.next_task_seq,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return _to_entity(row)

    async def rename(self, workspace_id: UUID, *, name: str, slug: str) -> Workspace:
        """Update name + slug atomically. The session flushes inside
        the call, so the service catches IntegrityError from the
        UNIQUE constraint on ``workspaces.name`` (or, in pathological
        cases, on ``workspaces.slug``) and surfaces a clean 409."""
        from app.domain.exceptions import WorkspaceNotFoundError

        row = await self._session.get(WorkspaceModel, workspace_id)
        if row is None:
            raise WorkspaceNotFoundError("workspace not found")
        row.name = name
        row.slug = slug
        await self._session.flush()
        await self._session.refresh(row)
        return _to_entity(row)

    async def allocate_next_task_seq(self, workspace_id: UUID) -> tuple[int, str]:
        """Atomically reserve the next per-workspace task seq.

        Returns ``(seq, prefix)`` so the caller can build the public id
        without a second round-trip. The increment is a single
        UPDATE ... RETURNING — Postgres serialises concurrent writers
        on the row lock, so two simultaneous task creations never
        collide on the (workspace_id, seq) unique index."""
        stmt = (
            update(WorkspaceModel)
            .where(WorkspaceModel.id == workspace_id)
            .values(next_task_seq=WorkspaceModel.next_task_seq + 1)
            .returning(WorkspaceModel.next_task_seq, WorkspaceModel.task_prefix)
        )
        result = await self._session.execute(stmt)
        row = result.one_or_none()
        if row is None:  # pragma: no cover - DI invariant
            raise RuntimeError(f"workspace {workspace_id} not found")
        # `next_task_seq` returned post-increment; the seq we hand out
        # is the pre-increment value.
        next_after, prefix = row
        return next_after - 1, prefix
