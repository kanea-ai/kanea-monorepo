from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import AgentStats, Member
from app.domain.enums import MemberType, TaskStatus
from app.infrastructure.db.models import MemberModel, TaskModel, TaskRatingModel


def _to_entity(row: MemberModel) -> Member:
    return Member(
        id=row.id,
        workspace_id=row.workspace_id,
        team_id=row.team_id,
        type=row.type,
        name=row.name,
        email=row.email,
        priority=row.priority,
        role=row.role,
        model=row.model,
        last_seen_at=row.last_seen_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlAlchemyMemberRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_email(self, email: str) -> Member | None:
        stmt = select(MemberModel).where(MemberModel.email == email)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _to_entity(row) if row is not None else None

    async def get_by_id(self, member_id: UUID) -> Member | None:
        row = await self._session.get(MemberModel, member_id)
        return _to_entity(row) if row is not None else None

    async def create(self, member: Member) -> Member:
        row = MemberModel(
            id=member.id,
            workspace_id=member.workspace_id,
            team_id=member.team_id,
            type=member.type,
            name=member.name,
            email=member.email,
            priority=member.priority,
            role=member.role,
            model=member.model,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return _to_entity(row)

    async def update(
        self,
        member_id: UUID,
        *,
        name: str | None = None,
        priority: int | None = None,
        model: str | None = None,
        clear_model: bool = False,
    ) -> Member:
        """Partial update: only fields explicitly passed are touched.
        `clear_model=True` is the explicit way to set model back to NULL
        (distinct from "didn't pass model")."""
        row = await self._session.get(MemberModel, member_id)
        if row is None:
            from app.domain.exceptions import AgentNotFoundError

            raise AgentNotFoundError("agent not found")
        if name is not None:
            row.name = name
        if priority is not None:
            row.priority = priority
        if clear_model:
            row.model = None
        elif model is not None:
            row.model = model
        await self._session.flush()
        await self._session.refresh(row)
        return _to_entity(row)

    async def delete(self, member_id: UUID) -> None:
        """Hard delete. Caller must verify FK preconditions
        (e.g. no tasks where the member is created_by_id) before invoking;
        the DB will raise IntegrityError on RESTRICT violations otherwise."""
        row = await self._session.get(MemberModel, member_id)
        if row is None:
            from app.domain.exceptions import AgentNotFoundError

            raise AgentNotFoundError("agent not found")
        await self._session.delete(row)
        await self._session.flush()

    async def heartbeat(self, member_id: UUID) -> None:
        """Stamp last_seen_at = now() on the member row. No-ops silently
        if the row is missing — heartbeats are best-effort signals, not
        commands; the caller's auth has already validated the principal."""
        row = await self._session.get(MemberModel, member_id)
        if row is None:
            return
        row.last_seen_at = datetime.now(UTC)
        await self._session.flush()

    async def list_for_workspace(self, workspace_id: UUID) -> list[Member]:
        stmt = (
            select(MemberModel)
            .where(MemberModel.workspace_id == workspace_id)
            .order_by(MemberModel.priority, MemberModel.created_at)
        )
        result = await self._session.execute(stmt)
        return [_to_entity(row) for row in result.scalars().all()]

    async def list_agents_for_workspace(self, workspace_id: UUID) -> list[Member]:
        stmt = (
            select(MemberModel)
            .where(
                MemberModel.workspace_id == workspace_id,
                MemberModel.type == MemberType.AGENT,
            )
            .order_by(MemberModel.priority, MemberModel.created_at)
        )
        result = await self._session.execute(stmt)
        return [_to_entity(row) for row in result.scalars().all()]

    async def has_created_tasks(self, member_id: UUID) -> bool:
        """Cheap existence check used by DELETE /agents/{id} to refuse
        deleting an agent that authored tasks (the FK on
        tasks.created_by_id is RESTRICT). Limit 1 is enough — we just
        need a yes/no."""
        stmt = select(TaskModel.id).where(TaskModel.created_by_id == member_id).limit(1)
        return (await self._session.execute(stmt)).first() is not None

    async def compute_agent_stats(self, agent_id: UUID) -> AgentStats:
        """Fold the per-agent stats into a small set of aggregations so
        the detail page is one round-trip per panel.

        Three queries: task aggregate, rating aggregate, last-activity
        max. Could be a single CTE but the readability cost outweighs the
        latency win for a workspace-sized table."""
        # Task aggregations: counts by status, sum of tokens, average
        # resolution time for DONE rows.
        task_stmt = select(
            func.count()
            .filter(
                and_(
                    TaskModel.status != TaskStatus.DONE,
                    TaskModel.status != TaskStatus.CANCELLED,
                )
            )
            .label("assigned"),
            func.count().filter(TaskModel.status == TaskStatus.DONE).label("completed"),
            func.coalesce(func.sum(TaskModel.tokens_used), 0).label("tokens"),
            func.avg(func.extract("epoch", TaskModel.completed_at - TaskModel.created_at))
            .filter(TaskModel.status == TaskStatus.DONE)
            .label("avg_seconds"),
        ).where(TaskModel.assignee_id == agent_id)
        task_row = (await self._session.execute(task_stmt)).one()

        # Average rating across this agent's rated tasks.
        rating_stmt = select(func.avg(TaskRatingModel.score)).where(
            TaskRatingModel.rated_member_id == agent_id
        )
        avg_score = (await self._session.execute(rating_stmt)).scalar_one_or_none()

        # Last activity: most recent updated_at across tasks where the
        # agent is either assignee or creator.
        last_stmt = select(func.max(TaskModel.updated_at)).where(
            or_(
                TaskModel.assignee_id == agent_id,
                TaskModel.created_by_id == agent_id,
            )
        )
        last_at = (await self._session.execute(last_stmt)).scalar_one_or_none()
        if last_at is not None and last_at.tzinfo is None:
            last_at = last_at.replace(tzinfo=UTC)

        avg_seconds = float(task_row.avg_seconds) if task_row.avg_seconds is not None else None
        accuracy = float(avg_score) if avg_score is not None else None

        return AgentStats(
            assigned_count=int(task_row.assigned or 0),
            completed_count=int(task_row.completed or 0),
            avg_resolution_seconds=avg_seconds,
            accuracy_percent=accuracy,
            last_activity_at=last_at if isinstance(last_at, datetime) else None,
            total_tokens_used=int(task_row.tokens or 0),
        )
