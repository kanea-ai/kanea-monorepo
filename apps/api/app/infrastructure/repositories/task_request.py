from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import TaskRequest
from app.domain.enums import RequestStatus
from app.infrastructure.db.models import TaskModel, TaskRequestModel


def _to_entity(row: TaskRequestModel) -> TaskRequest:
    return TaskRequest(
        id=row.id,
        source_task_id=row.source_task_id,
        requested_team_id=row.requested_team_id,
        requester_member_id=row.requester_member_id,
        suggested_title=row.suggested_title,
        suggested_description=row.suggested_description,
        justification=row.justification,
        status=RequestStatus(row.status),
        fulfilled_task_id=row.fulfilled_task_id,
        reject_reason=row.reject_reason,
        resolver_member_id=row.resolver_member_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        resolved_at=row.resolved_at,
    )


class SqlAlchemyTaskRequestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, request_id: UUID) -> TaskRequest | None:
        row = await self._session.get(TaskRequestModel, request_id)
        return _to_entity(row) if row is not None else None

    async def list_for_task(self, task_id: UUID) -> list[TaskRequest]:
        stmt = (
            select(TaskRequestModel)
            .where(TaskRequestModel.source_task_id == task_id)
            .order_by(TaskRequestModel.created_at, TaskRequestModel.id)
        )
        result = await self._session.execute(stmt)
        return [_to_entity(row) for row in result.scalars().all()]

    async def list_for_source_team(
        self,
        team_id: UUID,
        *,
        status: RequestStatus | None = None,
    ) -> list[TaskRequest]:
        """Outgoing-direction view: requests anchored to a source task
        on this team — what this team has asked other teams to do.

        Joined through ``tasks`` so the filter is on the source's
        ``team_id``, not the request's ``requested_team_id``. Use
        ``list_for_target_team`` for the incoming-direction inbox
        (requests targeting this team)."""
        stmt = (
            select(TaskRequestModel)
            .join(TaskModel, TaskModel.id == TaskRequestModel.source_task_id)
            .where(TaskModel.team_id == team_id)
        )
        if status is not None:
            stmt = stmt.where(TaskRequestModel.status == status.value)
        stmt = stmt.order_by(TaskRequestModel.created_at.desc(), TaskRequestModel.id)
        result = await self._session.execute(stmt)
        return [_to_entity(row) for row in result.scalars().all()]

    async def list_for_target_team(
        self,
        team_id: UUID,
        *,
        status: RequestStatus | None = None,
    ) -> list[TaskRequest]:
        """Incoming-direction inbox: requests whose ``requested_team_id``
        is this team — someone asked us for work.

        Uses the ``ix_task_requests_requested_team_id_status`` index on
        the ``task_requests`` table directly; no join needed."""
        stmt = select(TaskRequestModel).where(TaskRequestModel.requested_team_id == team_id)
        if status is not None:
            stmt = stmt.where(TaskRequestModel.status == status.value)
        stmt = stmt.order_by(TaskRequestModel.created_at.desc(), TaskRequestModel.id)
        result = await self._session.execute(stmt)
        return [_to_entity(row) for row in result.scalars().all()]

    async def list_fulfilled_by_task_ids(self, task_ids: list[UUID]) -> list[TaskRequest]:
        """Batch helper for the cross_team_origin denormalisation on
        TaskResponse. Returns every request whose ``fulfilled_task_id``
        is in ``task_ids`` — one round-trip regardless of list size."""
        if not task_ids:
            return []
        stmt = select(TaskRequestModel).where(TaskRequestModel.fulfilled_task_id.in_(task_ids))
        result = await self._session.execute(stmt)
        return [_to_entity(row) for row in result.scalars().all()]

    async def create(self, request: TaskRequest) -> TaskRequest:
        row = TaskRequestModel(
            id=request.id,
            source_task_id=request.source_task_id,
            requested_team_id=request.requested_team_id,
            requester_member_id=request.requester_member_id,
            suggested_title=request.suggested_title,
            suggested_description=request.suggested_description,
            justification=request.justification,
            status=request.status.value,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return _to_entity(row)

    async def mark_fulfilled(
        self,
        request_id: UUID,
        *,
        fulfilled_task_id: UUID,
        resolver_member_id: UUID,
        resolved_at,
    ) -> TaskRequest:
        from app.domain.exceptions import TaskRequestNotFoundError

        row = await self._session.get(TaskRequestModel, request_id)
        if row is None:
            raise TaskRequestNotFoundError("request not found")
        row.status = RequestStatus.FULFILLED.value
        row.fulfilled_task_id = fulfilled_task_id
        row.resolver_member_id = resolver_member_id
        row.resolved_at = resolved_at
        await self._session.flush()
        await self._session.refresh(row)
        return _to_entity(row)

    async def mark_rejected(
        self,
        request_id: UUID,
        *,
        reason: str | None,
        resolver_member_id: UUID,
        resolved_at,
    ) -> TaskRequest:
        from app.domain.exceptions import TaskRequestNotFoundError

        row = await self._session.get(TaskRequestModel, request_id)
        if row is None:
            raise TaskRequestNotFoundError("request not found")
        row.status = RequestStatus.REJECTED.value
        row.reject_reason = reason
        row.resolver_member_id = resolver_member_id
        row.resolved_at = resolved_at
        await self._session.flush()
        await self._session.refresh(row)
        return _to_entity(row)
