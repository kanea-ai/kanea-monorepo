from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import AgentStats, Member
from app.domain.enums import MemberRole, MemberType, TaskStatus, TeamRole
from app.infrastructure.db.models import MemberModel, TaskModel, TaskRatingModel


def _to_entity(row: MemberModel) -> Member:
    return Member(
        id=row.id,
        workspace_id=row.workspace_id,
        user_id=row.user_id,
        team_id=row.team_id,
        type=row.type,
        name=row.name,
        email=row.email,
        priority=row.priority,
        role=row.role,
        team_role=row.team_role,
        model=row.model,
        last_seen_at=row.last_seen_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlAlchemyMemberRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_email(self, email: str) -> Member | None:
        # Phase 1: a single email can map to multiple memberships
        # (one per workspace). Auth no longer routes through this; it
        # uses UserRepository.get_by_email instead. Kept for the
        # invite-accept duplicate check, which expects at most one row
        # per workspace because of uq_members_workspace_id_email.
        # Picks the earliest membership when more than one exists.
        stmt = (
            select(MemberModel)
            .where(MemberModel.email == email)
            .order_by(MemberModel.created_at)
            .limit(1)
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _to_entity(row) if row is not None else None

    async def list_for_user(self, user_id: UUID) -> list[Member]:
        """All memberships a global User holds. Drives the
        multi-workspace login picker."""
        stmt = (
            select(MemberModel)
            .where(MemberModel.user_id == user_id)
            .order_by(MemberModel.created_at, MemberModel.id)
        )
        result = await self._session.execute(stmt)
        return [_to_entity(row) for row in result.scalars().all()]

    async def get_by_id(self, member_id: UUID) -> Member | None:
        row = await self._session.get(MemberModel, member_id)
        return _to_entity(row) if row is not None else None

    async def create(self, member: Member) -> Member:
        row = MemberModel(
            id=member.id,
            workspace_id=member.workspace_id,
            user_id=member.user_id,
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

    async def set_team(
        self,
        member_id: UUID,
        *,
        team_id: UUID | None,
        team_role: TeamRole | None,
    ) -> Member:
        """Assign / unassign a member to a team. Setting team_id to
        None clears the team and the role. Setting team_id requires a
        non-None team_role — the service layer enforces that."""
        from app.domain.exceptions import InvalidMemberTypeError

        row = await self._session.get(MemberModel, member_id)
        if row is None:
            raise InvalidMemberTypeError("member not found")
        row.team_id = team_id
        row.team_role = team_role
        await self._session.flush()
        await self._session.refresh(row)
        return _to_entity(row)

    async def heartbeat(self, member_id: UUID) -> None:
        """Stamp last_seen_at = now() on the member row. No-ops silently
        if the row is missing — heartbeats are best-effort signals, not
        commands; the caller's auth has already validated the principal."""
        row = await self._session.get(MemberModel, member_id)
        if row is None:
            return
        row.last_seen_at = datetime.now(UTC)
        await self._session.flush()

    async def list_humans_by_email_locals(
        self, workspace_id: UUID, locals_lc: list[str]
    ) -> list[Member]:
        """Mention-resolver lookup. Returns HUMAN members in the
        workspace whose email's local-part matches one of the
        provided lower-cased handles. Empty input → empty list."""
        if not locals_lc:
            return []
        # Postgres SPLIT_PART(email, '@', 1) gets the local-part; we
        # lower-case it for the comparison so '@Alice' resolves the
        # same as '@alice'. Agents have no email and no User row, so
        # the type filter is the belt to the JOIN's brace.
        stmt = (
            select(MemberModel)
            .where(MemberModel.workspace_id == workspace_id)
            .where(MemberModel.type == MemberType.HUMAN)
            .where(MemberModel.email.is_not(None))
            .where(func.lower(func.split_part(MemberModel.email, "@", 1)).in_(locals_lc))
        )
        result = await self._session.execute(stmt)
        return [_to_entity(row) for row in result.scalars().all()]

    async def list_for_workspace(
        self,
        workspace_id: UUID,
        *,
        name: str | None = None,
        member_id: UUID | None = None,
        role: MemberRole | None = None,
        team_id: UUID | None = None,
        project_id: UUID | None = None,
        humans_only: bool = False,
        visibility_team_id: UUID | None = None,
        visibility_self_id: UUID | None = None,
    ) -> list[Member]:
        stmt = select(MemberModel).where(MemberModel.workspace_id == workspace_id)

        # Narrowing filters (applied first; see service for visibility).
        if name is not None and name != "":
            stmt = stmt.where(MemberModel.name.ilike(f"%{name}%"))
        if member_id is not None:
            stmt = stmt.where(MemberModel.id == member_id)
        if role is not None:
            stmt = stmt.where(MemberModel.role == role)
        if team_id is not None:
            stmt = stmt.where(MemberModel.team_id == team_id)
        if humans_only:
            stmt = stmt.where(MemberModel.type == MemberType.HUMAN)
        if project_id is not None:
            # "Members assigned to at least one task in the project."
            project_member_ids = (
                select(TaskModel.assignee_id)
                .where(TaskModel.project_id == project_id)
                .where(TaskModel.assignee_id.is_not(None))
                .distinct()
            )
            stmt = stmt.where(MemberModel.id.in_(project_member_ids))

        # Visibility scope: union of "members on this team" and "self".
        # Either may be None — if both are None we leave the listing
        # workspace-wide (admins / owners).
        if visibility_team_id is not None or visibility_self_id is not None:
            scope_clauses = []
            if visibility_team_id is not None:
                scope_clauses.append(MemberModel.team_id == visibility_team_id)
            if visibility_self_id is not None:
                scope_clauses.append(MemberModel.id == visibility_self_id)
            stmt = stmt.where(or_(*scope_clauses))

        stmt = stmt.order_by(MemberModel.priority, MemberModel.created_at)
        result = await self._session.execute(stmt)
        return [_to_entity(row) for row in result.scalars().all()]

    async def update_profile(
        self,
        member_id: UUID,
        *,
        name: str | None = None,
        role: MemberRole | None = None,
        priority: int | None = None,
    ) -> Member:
        """Admin-side edit of a member's display name, workspace role,
        and/or priority. Distinct from `update()` (which is for agent-
        only fields). Raises if the row is missing — callers verify
        existence + the last-OWNER invariant before calling."""
        from app.domain.exceptions import InvalidMemberTypeError

        row = await self._session.get(MemberModel, member_id)
        if row is None:
            raise InvalidMemberTypeError("member not found")
        if name is not None:
            row.name = name
        if role is not None:
            row.role = role
        if priority is not None:
            row.priority = priority
        await self._session.flush()
        await self._session.refresh(row)
        return _to_entity(row)

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
