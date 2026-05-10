from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError

from app.application.auth.ports import MemberRepository
from app.application.pagination import Page
from app.application.projects.ports import ProjectRepository
from app.application.projects.schemas import (
    CreateProjectRequest,
    ProjectHistoryResponse,
    ProjectHistorySummary,
    ProjectResponse,
    ProjectTaskHistory,
    UpdateProjectRequest,
)
from app.application.tasks.ports import (
    TaskActivityRepository,
    TaskCommentRepository,
    TaskRatingRepository,
    TaskRepository,
)
from app.application.tasks.schemas import (
    ActivityResponse,
    CommentResponse,
    Principal,
    TaskRatingResponse,
)
from app.application.tenants.ports import WorkspaceReadRepository
from app.domain.entities import Project, TaskActivity, TaskComment
from app.domain.enums import ProjectStatus, TaskStatus
from app.domain.exceptions import ProjectNameConflictError, ProjectNotFoundError


@dataclass(slots=True)
class ProjectService:
    projects: ProjectRepository
    # Optional dependencies — the history endpoint needs them, but the
    # CRUD paths don't, so legacy DI / unit tests can construct
    # ProjectService(projects=...) and skip them.
    tasks: TaskRepository | None = None
    activities: TaskActivityRepository | None = None
    comments: TaskCommentRepository | None = None
    ratings: TaskRatingRepository | None = None
    members: MemberRepository | None = None
    workspaces: WorkspaceReadRepository | None = None

    async def list_for_workspace(
        self,
        principal: Principal,
        *,
        include_archived: bool = False,
        skip: int = 0,
        limit: int | None = None,
    ) -> Page[ProjectResponse]:
        rows, total = await self.projects.list_for_workspace(
            principal.workspace_id,
            include_archived=include_archived,
            skip=skip,
            limit=limit,
        )
        return Page[ProjectResponse](
            items=[ProjectResponse.from_entity(r) for r in rows], total=total
        )

    async def get_by_id(self, project_id: UUID, principal: Principal) -> ProjectResponse:
        project = await self._load_workspace_project(project_id, principal)
        return ProjectResponse.from_entity(project)

    async def create(self, request: CreateProjectRequest, principal: Principal) -> ProjectResponse:
        try:
            project = await self.projects.create(
                Project(
                    id=uuid4(),
                    workspace_id=principal.workspace_id,
                    name=request.name,
                    description=request.description,
                    status=ProjectStatus.ACTIVE,
                )
            )
        except IntegrityError as exc:
            raise ProjectNameConflictError(
                "a project with that name already exists in this workspace"
            ) from exc
        return ProjectResponse.from_entity(project)

    async def update(
        self,
        project_id: UUID,
        request: UpdateProjectRequest,
        principal: Principal,
    ) -> ProjectResponse:
        await self._load_workspace_project(project_id, principal)
        clear_description = (
            "description" in request.model_fields_set and request.description is None
        )
        try:
            updated = await self.projects.update(
                project_id,
                name=request.name,
                description=request.description if not clear_description else None,
                status=request.status,
                clear_description=clear_description,
            )
        except IntegrityError as exc:
            raise ProjectNameConflictError(
                "a project with that name already exists in this workspace"
            ) from exc
        return ProjectResponse.from_entity(updated)

    async def delete(self, project_id: UUID, principal: Principal) -> None:
        """Hard delete. Tasks pointing at the project get their
        project_id set to NULL via the FK CASCADE, so they survive
        as un-projected backlog items rather than disappearing."""
        await self._load_workspace_project(project_id, principal)
        await self.projects.delete(project_id)

    async def compute_history(
        self, project_id: UUID, principal: Principal
    ) -> ProjectHistoryResponse:
        """Single-shot bundle for the AI history endpoint.

        Loads the project, all its tasks, the audit log per task, the
        comment thread per task, and the (optional) issuer rating per
        task. Computes a per-project summary that highlights what an
        agent should look at first: status mix, blocked count, average
        resolution, total tokens, average rating.
        """
        if (
            self.tasks is None
            or self.activities is None
            or self.comments is None
            or self.ratings is None
            or self.members is None
            or self.workspaces is None
        ):  # pragma: no cover - DI invariant
            raise RuntimeError("history dependencies not wired")

        project = await self._load_workspace_project(project_id, principal)

        workspace = await self.workspaces.get_by_id(principal.workspace_id)
        prefix = workspace.task_prefix if workspace is not None else "TASK"

        tasks = await self.tasks.list_by_workspace(principal.workspace_id, project_id=project.id)

        task_histories: list[ProjectTaskHistory] = []
        by_status: dict[str, int] = {s.value: 0 for s in TaskStatus}
        blocked_now = 0
        total_tokens = 0
        rated_scores: list[int] = []
        resolution_seconds: list[float] = []

        for task in tasks:
            by_status[task.status.value] += 1
            if task.is_blocked:
                blocked_now += 1
            total_tokens += task.tokens_used
            if task.completed_at is not None and task.created_at is not None:
                resolution_seconds.append((task.completed_at - task.created_at).total_seconds())

            activities_raw = await self.activities.list_for_task(task.id)
            activities = [await self._activity_to_response(a) for a in activities_raw]

            comments_raw = await self.comments.list_for_task(task.id)
            comments = [await self._comment_to_response(c) for c in comments_raw]

            rating_entity = await self.ratings.get_for_task(task.id)
            rating = (
                TaskRatingResponse(
                    task_id=rating_entity.task_id,
                    rated_by_id=rating_entity.rated_by_id,
                    rated_member_id=rating_entity.rated_member_id,
                    score=rating_entity.score,
                    feedback=rating_entity.feedback,
                    created_at=rating_entity.created_at,
                )
                if rating_entity is not None
                else None
            )
            if rating_entity is not None:
                rated_scores.append(rating_entity.score)

            task_histories.append(
                ProjectTaskHistory(
                    id=task.id,
                    public_id=(f"{prefix}-{task.seq:03d}" if task.seq else f"{prefix}-000"),
                    title=task.title,
                    status=task.status,
                    is_blocked=task.is_blocked,
                    blocked_reason=task.blocked_reason,
                    description=task.description,
                    priority=task.priority,
                    assignee_id=task.assignee_id,
                    project_id=task.project_id,
                    team_id=task.team_id,
                    tokens_used=task.tokens_used,
                    created_at=task.created_at,
                    completed_at=task.completed_at,
                    rating=rating,
                    activities=activities,
                    comments=comments,
                )
            )

        summary = ProjectHistorySummary(
            total_tasks=len(tasks),
            by_status=by_status,
            blocked_now=blocked_now,
            avg_resolution_seconds=(
                sum(resolution_seconds) / len(resolution_seconds) if resolution_seconds else None
            ),
            total_tokens_used=total_tokens,
            rated_count=len(rated_scores),
            avg_rating=(sum(rated_scores) / len(rated_scores) if rated_scores else None),
        )

        return ProjectHistoryResponse(
            project=ProjectResponse.from_entity(project),
            summary=summary,
            tasks=task_histories,
        )

    async def _activity_to_response(self, row: TaskActivity) -> ActivityResponse:
        actor_name: str | None = None
        if row.actor_member_id is not None and self.members is not None:
            actor = await self.members.get_by_id(row.actor_member_id)
            actor_name = actor.name if actor is not None else None
        return ActivityResponse(
            id=row.id,
            task_id=row.task_id,
            actor_member_id=row.actor_member_id,
            actor_name=actor_name,
            event_type=row.event_type,
            payload=row.payload,
            created_at=row.created_at,
        )

    async def _comment_to_response(self, row: TaskComment) -> CommentResponse:
        author_name: str | None = None
        if row.author_member_id is not None and self.members is not None:
            author = await self.members.get_by_id(row.author_member_id)
            author_name = author.name if author is not None else None
        return CommentResponse(
            id=row.id,
            task_id=row.task_id,
            author_member_id=row.author_member_id,
            author_name=author_name,
            body=row.body,
            created_at=row.created_at,
        )

    async def _load_workspace_project(self, project_id: UUID, principal: Principal) -> Project:
        project = await self.projects.get_by_id(project_id)
        if project is None or project.workspace_id != principal.workspace_id:
            raise ProjectNotFoundError("project not found")
        return project
