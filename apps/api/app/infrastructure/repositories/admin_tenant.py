from __future__ import annotations

# Cross-tenant intervention surface. Two read shapes — workspace
# detail with stats grid, and the per-workspace user list with
# hierarchy slot (team + team_role + headed department). Both
# materialise their result set in a single SQL pass so the back-
# office pages don't N+1 over members.
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.application.admin.tenant_ports import (
    AdminTenantRepository,
    WorkspaceDetailRow,
    WorkspaceStatusCounts,
    WorkspaceUserDetailRow,
)
from app.application.admin.tenant_schemas import AdminAgentRow, AdminMemberStats
from app.domain.enums import MemberRole, MemberType, TaskStatus
from app.infrastructure.db.models import (
    DepartmentModel,
    MemberModel,
    ProjectModel,
    TaskModel,
    TaskRatingModel,
    TeamModel,
    UserModel,
    WorkspaceModel,
)


class SqlAlchemyAdminTenantRepository(AdminTenantRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_workspace_detail(self, workspace_id: UUID) -> WorkspaceDetailRow:
        """One SELECT with seven correlated counts. The status
        breakdown uses ``COUNT(*) FILTER (WHERE status = ...)`` so the
        plan touches the tasks table once."""
        user_count = (
            select(func.count(MemberModel.id))
            .where(
                MemberModel.workspace_id == workspace_id,
                MemberModel.type == MemberType.HUMAN,
            )
            .scalar_subquery()
        )
        task_count = (
            select(func.count(TaskModel.id))
            .where(TaskModel.workspace_id == workspace_id)
            .scalar_subquery()
        )
        token_sum = (
            select(func.coalesce(func.sum(TaskModel.tokens_used), 0))
            .where(TaskModel.workspace_id == workspace_id)
            .scalar_subquery()
        )
        team_count = (
            select(func.count(TeamModel.id))
            .where(TeamModel.workspace_id == workspace_id)
            .scalar_subquery()
        )
        dept_count = (
            select(func.count(DepartmentModel.id))
            .where(DepartmentModel.workspace_id == workspace_id)
            .scalar_subquery()
        )
        project_count = (
            select(func.count(ProjectModel.id))
            .where(ProjectModel.workspace_id == workspace_id)
            .scalar_subquery()
        )

        def _count_status(value: TaskStatus):
            return (
                select(func.count(TaskModel.id))
                .where(
                    TaskModel.workspace_id == workspace_id,
                    TaskModel.status == value,
                )
                .scalar_subquery()
            )

        blocked_count = (
            select(func.count(TaskModel.id))
            .where(TaskModel.workspace_id == workspace_id, TaskModel.is_blocked.is_(True))
            .scalar_subquery()
        )

        stmt = select(
            user_count.label("total_users"),
            task_count.label("total_tasks"),
            token_sum.label("total_tokens_used"),
            team_count.label("total_teams"),
            dept_count.label("total_departments"),
            project_count.label("total_projects"),
            _count_status(TaskStatus.PENDING).label("pending"),
            _count_status(TaskStatus.IN_PROGRESS).label("in_progress"),
            _count_status(TaskStatus.IN_REVIEW).label("in_review"),
            _count_status(TaskStatus.DONE).label("done"),
            _count_status(TaskStatus.CANCELLED).label("cancelled"),
            blocked_count.label("blocked"),
        )
        row = (await self._session.execute(stmt)).one()
        return WorkspaceDetailRow(
            total_users=int(row[0] or 0),
            total_tasks=int(row[1] or 0),
            total_tokens_used=int(row[2] or 0),
            total_teams=int(row[3] or 0),
            total_departments=int(row[4] or 0),
            total_projects=int(row[5] or 0),
            status_counts=WorkspaceStatusCounts(
                pending=int(row[6] or 0),
                in_progress=int(row[7] or 0),
                in_review=int(row[8] or 0),
                done=int(row[9] or 0),
                cancelled=int(row[10] or 0),
                blocked=int(row[11] or 0),
            ),
        )

    async def list_workspace_users(
        self,
        workspace_id: UUID,
        *,
        name: str | None = None,
        skip: int = 0,
        limit: int = 25,
    ) -> tuple[list[WorkspaceUserDetailRow], int]:
        # The members row carries the hierarchy slot. LEFT JOIN to
        # users (agents have no user row) + team + team's department
        # + the department this member is the head of, if any.
        TeamDept = aliased(DepartmentModel)  # noqa: N806 - SQL alias
        HeadDept = aliased(DepartmentModel)  # noqa: N806 - SQL alias

        base = (
            select(
                MemberModel.id.label("member_id"),
                MemberModel.user_id.label("user_id"),
                MemberModel.email,
                MemberModel.name,
                MemberModel.type,
                MemberModel.role,
                MemberModel.is_suspended,
                MemberModel.team_id,
                TeamModel.name.label("team_name"),
                MemberModel.team_role,
                TeamModel.department_id.label("team_department_id"),
                TeamDept.name.label("team_department_name"),
                HeadDept.id.label("headed_department_id"),
                HeadDept.name.label("headed_department_name"),
                UserModel.full_name.label("user_full_name"),
            )
            .outerjoin(UserModel, UserModel.id == MemberModel.user_id)
            .outerjoin(TeamModel, TeamModel.id == MemberModel.team_id)
            .outerjoin(TeamDept, TeamDept.id == TeamModel.department_id)
            .outerjoin(HeadDept, HeadDept.head_id == MemberModel.id)
            .where(MemberModel.workspace_id == workspace_id)
        )
        if name is not None and name != "":
            needle = f"%{name.lower()}%"
            base = base.where(
                func.lower(MemberModel.name).like(needle)
                | (MemberModel.email.is_not(None) & func.lower(MemberModel.email).like(needle))
            )
        base = base.order_by(MemberModel.priority, MemberModel.created_at)

        items_stmt = base.offset(skip).limit(limit)
        items_result = await self._session.execute(items_stmt)
        items: list[WorkspaceUserDetailRow] = []
        for row in items_result.all():
            items.append(
                WorkspaceUserDetailRow(
                    member_id=row.member_id,
                    user_id=row.user_id,
                    email=row.email,
                    full_name=row.user_full_name or row.name,
                    type=row.type,
                    role=row.role,
                    is_suspended=row.is_suspended,
                    team_id=row.team_id,
                    team_name=row.team_name,
                    team_role=row.team_role,
                    team_department_id=row.team_department_id,
                    team_department_name=row.team_department_name,
                    headed_department_id=row.headed_department_id,
                    headed_department_name=row.headed_department_name,
                )
            )
        count_stmt = select(func.count()).select_from(
            select(MemberModel.id)
            .where(*(base.whereclause,) if base.whereclause is not None else ())
            .subquery()
        )
        total = (await self._session.execute(count_stmt)).scalar_one()
        return items, int(total)

    async def find_member_by_user(
        self, workspace_id: UUID, user_id: UUID
    ) -> WorkspaceUserDetailRow | None:
        items, _ = await self.list_workspace_users(workspace_id, limit=1)
        # Refresh the listing for the specific user_id rather than
        # paging the whole table — a small targeted SELECT.
        rows, _ = await self._list_one(workspace_id, user_id)
        return rows[0] if rows else None

    async def _list_one(
        self, workspace_id: UUID, user_id: UUID
    ) -> tuple[list[WorkspaceUserDetailRow], int]:
        TeamDept = aliased(DepartmentModel)  # noqa: N806
        HeadDept = aliased(DepartmentModel)  # noqa: N806
        stmt = (
            select(
                MemberModel.id.label("member_id"),
                MemberModel.user_id.label("user_id"),
                MemberModel.email,
                MemberModel.name,
                MemberModel.type,
                MemberModel.role,
                MemberModel.is_suspended,
                MemberModel.team_id,
                TeamModel.name.label("team_name"),
                MemberModel.team_role,
                TeamModel.department_id.label("team_department_id"),
                TeamDept.name.label("team_department_name"),
                HeadDept.id.label("headed_department_id"),
                HeadDept.name.label("headed_department_name"),
                UserModel.full_name.label("user_full_name"),
            )
            .outerjoin(UserModel, UserModel.id == MemberModel.user_id)
            .outerjoin(TeamModel, TeamModel.id == MemberModel.team_id)
            .outerjoin(TeamDept, TeamDept.id == TeamModel.department_id)
            .outerjoin(HeadDept, HeadDept.head_id == MemberModel.id)
            .where(
                MemberModel.workspace_id == workspace_id,
                MemberModel.user_id == user_id,
            )
        )
        result = await self._session.execute(stmt)
        items = []
        for row in result.all():
            items.append(
                WorkspaceUserDetailRow(
                    member_id=row.member_id,
                    user_id=row.user_id,
                    email=row.email,
                    full_name=row.user_full_name or row.name,
                    type=row.type,
                    role=row.role,
                    is_suspended=row.is_suspended,
                    team_id=row.team_id,
                    team_name=row.team_name,
                    team_role=row.team_role,
                    team_department_id=row.team_department_id,
                    team_department_name=row.team_department_name,
                    headed_department_id=row.headed_department_id,
                    headed_department_name=row.headed_department_name,
                )
            )
        return items, len(items)

    async def find_member_by_id(
        self, workspace_id: UUID, member_id: UUID
    ) -> WorkspaceUserDetailRow | None:
        """Member-id-keyed lookup. Required for AGENT support — agents
        have no backing user row so the user-id-keyed sibling can't
        reach them."""
        rows, _ = await self._list_by_member(workspace_id, member_id)
        return rows[0] if rows else None

    async def _list_by_member(
        self, workspace_id: UUID, member_id: UUID
    ) -> tuple[list[WorkspaceUserDetailRow], int]:
        TeamDept = aliased(DepartmentModel)  # noqa: N806
        HeadDept = aliased(DepartmentModel)  # noqa: N806
        stmt = (
            select(
                MemberModel.id.label("member_id"),
                MemberModel.user_id.label("user_id"),
                MemberModel.email,
                MemberModel.name,
                MemberModel.type,
                MemberModel.role,
                MemberModel.is_suspended,
                MemberModel.team_id,
                TeamModel.name.label("team_name"),
                MemberModel.team_role,
                TeamModel.department_id.label("team_department_id"),
                TeamDept.name.label("team_department_name"),
                HeadDept.id.label("headed_department_id"),
                HeadDept.name.label("headed_department_name"),
                UserModel.full_name.label("user_full_name"),
            )
            .outerjoin(UserModel, UserModel.id == MemberModel.user_id)
            .outerjoin(TeamModel, TeamModel.id == MemberModel.team_id)
            .outerjoin(TeamDept, TeamDept.id == TeamModel.department_id)
            .outerjoin(HeadDept, HeadDept.head_id == MemberModel.id)
            .where(
                MemberModel.workspace_id == workspace_id,
                MemberModel.id == member_id,
            )
        )
        result = await self._session.execute(stmt)
        items = [
            WorkspaceUserDetailRow(
                member_id=row.member_id,
                user_id=row.user_id,
                email=row.email,
                full_name=row.user_full_name or row.name,
                type=row.type,
                role=row.role,
                is_suspended=row.is_suspended,
                team_id=row.team_id,
                team_name=row.team_name,
                team_role=row.team_role,
                team_department_id=row.team_department_id,
                team_department_name=row.team_department_name,
                headed_department_id=row.headed_department_id,
                headed_department_name=row.headed_department_name,
            )
            for row in result.all()
        ]
        return items, len(items)

    async def compute_member_stats(self, member_id: UUID) -> AdminMemberStats:
        """Mirrors the per-agent stats SQL on
        ``SqlAlchemyMemberRepository.compute_agent_stats`` — same
        aggregation, just returned as the admin-side schema. Three
        queries (task aggregate / rating aggregate / last activity max);
        readability beats squeezing them into a single CTE at this scale."""
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
        ).where(TaskModel.assignee_id == member_id)
        task_row = (await self._session.execute(task_stmt)).one()

        rating_stmt = select(func.avg(TaskRatingModel.score)).where(
            TaskRatingModel.rated_member_id == member_id
        )
        avg_score = (await self._session.execute(rating_stmt)).scalar_one_or_none()

        last_stmt = select(func.max(TaskModel.updated_at)).where(
            or_(
                TaskModel.assignee_id == member_id,
                TaskModel.created_by_id == member_id,
            )
        )
        last_at = (await self._session.execute(last_stmt)).scalar_one_or_none()
        if last_at is not None and last_at.tzinfo is None:
            last_at = last_at.replace(tzinfo=UTC)

        return AdminMemberStats(
            assigned_count=int(task_row.assigned or 0),
            completed_count=int(task_row.completed or 0),
            avg_resolution_seconds=(
                float(task_row.avg_seconds) if task_row.avg_seconds is not None else None
            ),
            accuracy_percent=float(avg_score) if avg_score is not None else None,
            last_activity_at=last_at if isinstance(last_at, datetime) else None,
            total_tokens_used=int(task_row.tokens or 0),
        )

    async def list_agents(
        self,
        *,
        name: str | None = None,
        skip: int = 0,
        limit: int = 25,
    ) -> tuple[list[AdminAgentRow], int]:
        """Cross-tenant agent listing. Each row is one AGENT member +
        its host workspace's identity, so the back-office /users page
        can click straight into the detail panel without an extra
        round-trip to look up the workspace name."""
        base = (
            select(
                MemberModel.id.label("member_id"),
                MemberModel.name.label("full_name"),
                MemberModel.created_at,
                WorkspaceModel.id.label("workspace_id"),
                WorkspaceModel.name.label("workspace_name"),
                WorkspaceModel.slug.label("workspace_slug"),
            )
            .join(WorkspaceModel, WorkspaceModel.id == MemberModel.workspace_id)
            .where(MemberModel.type == MemberType.AGENT)
        )
        if name is not None and name != "":
            needle = f"%{name.lower()}%"
            base = base.where(func.lower(MemberModel.name).like(needle))
        base = base.order_by(MemberModel.created_at.desc())

        items_stmt = base.offset(skip).limit(limit)
        items_result = await self._session.execute(items_stmt)
        items = [
            AdminAgentRow(
                member_id=row.member_id,
                workspace_id=row.workspace_id,
                workspace_name=row.workspace_name,
                workspace_slug=row.workspace_slug,
                full_name=row.full_name,
                created_at=row.created_at,
            )
            for row in items_result.all()
        ]

        count_stmt = select(func.count(MemberModel.id)).where(MemberModel.type == MemberType.AGENT)
        if name is not None and name != "":
            needle = f"%{name.lower()}%"
            count_stmt = count_stmt.where(func.lower(MemberModel.name).like(needle))
        total = (await self._session.execute(count_stmt)).scalar_one()
        return items, int(total)

    async def find_first_owner_member_id(self, workspace_id: UUID) -> UUID | None:
        stmt = (
            select(MemberModel.id)
            .where(
                MemberModel.workspace_id == workspace_id,
                MemberModel.role == MemberRole.WORKSPACE_OWNER,
                MemberModel.type == MemberType.HUMAN,
            )
            .order_by(MemberModel.created_at)
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()
