from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import AuditLog
from app.domain.enums import AuditAction, AuditResourceType
from app.infrastructure.db.models import AuditLogModel


def _to_entity(row: AuditLogModel) -> AuditLog:
    return AuditLog(
        id=row.id,
        workspace_id=row.workspace_id,
        actor_member_id=row.actor_member_id,
        # Stored as varchar — narrow to the enum here. If the DB
        # carries a value the enum doesn't know yet (e.g. a future
        # action written by a newer worker), surface the raw string
        # so the read path stays robust.
        action=AuditAction(row.action),
        resource_type=AuditResourceType(row.resource_type),
        resource_id=row.resource_id,
        changes=row.changes or {},
        created_at=row.created_at,
    )


class SqlAlchemyAuditLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, log: AuditLog) -> AuditLog:
        row = AuditLogModel(
            id=log.id,
            workspace_id=log.workspace_id,
            actor_member_id=log.actor_member_id,
            action=log.action.value,
            resource_type=log.resource_type.value,
            resource_id=log.resource_id,
            changes=log.changes,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return _to_entity(row)

    async def list_for_workspace(
        self,
        workspace_id: UUID,
        *,
        resource_types: list[AuditResourceType] | None = None,
        team_resource_ids: list[UUID] | None = None,
        limit: int = 100,
        before: UUID | None = None,
    ) -> list[AuditLog]:
        stmt = select(AuditLogModel).where(AuditLogModel.workspace_id == workspace_id)

        # Empty resource_types list = the caller wants zero rows. We
        # short-circuit so we don't issue a wasted query.
        if resource_types is not None:
            if not resource_types:
                return []
            stmt = stmt.where(AuditLogModel.resource_type.in_([rt.value for rt in resource_types]))

        # team_resource_ids narrows TEAM-typed rows to a specific set.
        # Other resource types (if allowed by ``resource_types``) are
        # unaffected.
        if team_resource_ids is not None:
            if not team_resource_ids:
                # Caller wants TEAM rows narrowed to nothing — and
                # because the only allowed resource_type was TEAM in
                # the priority-3 path, the answer is zero rows.
                return []
            stmt = stmt.where(
                (AuditLogModel.resource_type != AuditResourceType.TEAM.value)
                | (AuditLogModel.resource_id.in_(team_resource_ids))
            )

        if before is not None:
            # Cursor pagination on (created_at, id). The ix_audit_logs_
            # workspace_created index makes this cheap.
            cursor_row_stmt = select(AuditLogModel.created_at, AuditLogModel.id).where(
                AuditLogModel.id == before
            )
            cursor_row = (await self._session.execute(cursor_row_stmt)).first()
            if cursor_row is not None:
                cursor_created_at, cursor_id = cursor_row
                stmt = stmt.where(
                    (AuditLogModel.created_at < cursor_created_at)
                    | (
                        (AuditLogModel.created_at == cursor_created_at)
                        & (AuditLogModel.id < cursor_id)
                    )
                )

        stmt = stmt.order_by(AuditLogModel.created_at.desc(), AuditLogModel.id.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return [_to_entity(row) for row in result.scalars().all()]
