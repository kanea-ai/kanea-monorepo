from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from app.application.auth.ports import MemberRepository
from app.application.projects.ports import ProjectRepository
from app.application.tasks.ports import (
    TaskCommentRepository,
    TaskRatingRepository,
    TaskRelationRepository,
    TaskRepository,
    WorkspaceTaskSeqRepository,
)
from app.application.tasks.schemas import (
    CommentResponse,
    CreateCommentRequest,
    CreateRelationRequest,
    CreateTaskRequest,
    DelegateTaskRequest,
    Principal,
    RateTaskRequest,
    RelationItem,
    SetBlockedRequest,
    TaskDetailResponse,
    TaskRatingResponse,
    TaskRelationsResponse,
    TaskResponse,
    UpdateTaskLinksRequest,
    UpdateTaskStatusRequest,
)
from app.application.teams.ports import TeamRepository
from app.application.tenants.ports import WorkspaceReadRepository
from app.domain.entities import Member, Task, TaskComment, TaskRating, TaskRelation
from app.domain.enums import TaskRelationType, TaskStatus
from app.domain.exceptions import (
    DelegationForbiddenError,
    InvalidStatusTransitionError,
    ProjectNotFoundError,
    RatingForbiddenError,
    TaskAlreadyRatedError,
    TaskNotFoundError,
    TaskNotInDoneStateError,
    TaskRelationAlreadyExistsError,
    TaskRelationNotFoundError,
    TaskRelationSelfLinkError,
    TeamNotFoundError,
)

# Allowed status transitions. Any transition not listed here is rejected.
# BLOCKED is no longer a status — being blocked is an orthogonal flag,
# toggled via PATCH /tasks/{id}/block. The lifecycle stays linear.
_ALLOWED_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.PENDING: frozenset({TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED}),
    TaskStatus.IN_PROGRESS: frozenset({TaskStatus.DONE, TaskStatus.CANCELLED, TaskStatus.PENDING}),
    TaskStatus.DONE: frozenset(),
    TaskStatus.CANCELLED: frozenset(),
}


@dataclass(slots=True)
class TaskService:
    tasks: TaskRepository
    members: MemberRepository
    workspaces: WorkspaceReadRepository
    seq_allocator: WorkspaceTaskSeqRepository
    # Optional so existing call-sites that don't construct ratings (tests,
    # legacy DI paths) keep working. The rate_task() entry-point checks
    # for None and raises a clear error if it's invoked without one.
    ratings: TaskRatingRepository | None = None
    comments: TaskCommentRepository | None = None
    relations: TaskRelationRepository | None = None
    # Project / team lookups happen at create + move time so we can
    # 404 cross-tenant ids instead of letting the FK silently accept.
    projects: ProjectRepository | None = None
    team_lookup: TeamRepository | None = None

    async def delegate(
        self,
        task_id: UUID,
        request: DelegateTaskRequest,
        requester: Principal,
    ) -> TaskResponse:
        task = await self._load_task(task_id, requester)
        target = await self._load_target(request.member_id, requester)
        self._enforce_hierarchy(requester, target)

        updated = await self.tasks.assign(task_id=task.id, assignee_id=target.id)
        prefix = await self._workspace_prefix(requester.workspace_id)
        return TaskResponse.from_entity(updated, prefix=prefix)

    async def list_for_workspace(
        self,
        requester: Principal,
        *,
        status: TaskStatus | None = None,
        blocked_only: bool = False,
        project_id: UUID | None = None,
        team_id: UUID | None = None,
    ) -> list[TaskResponse]:
        rows = await self.tasks.list_by_workspace(
            requester.workspace_id,
            status=status,
            blocked_only=blocked_only,
            project_id=project_id,
            team_id=team_id,
        )
        prefix = await self._workspace_prefix(requester.workspace_id)
        return [TaskResponse.from_entity(row, prefix=prefix) for row in rows]

    async def get_by_id(self, task_id: UUID, requester: Principal) -> TaskDetailResponse:
        """Returns the task plus its full relation graph. Agents reading
        a task get the linked-work context (blocks / blocked_by / etc.)
        in a single round-trip; the standalone /relations endpoint is
        kept for callers that only want the buckets."""
        task = await self._load_task(task_id, requester)
        prefix = await self._workspace_prefix(requester.workspace_id)

        # Relations are best-effort: if the relations repo isn't wired
        # (legacy DI), fall back to an empty grouping rather than 500.
        if self.relations is not None:
            rows = await self.relations.list_for_task(task.id)
            grouped = await self._group_relations(task.id, rows, requester)
        else:
            grouped = TaskRelationsResponse(
                blocks=[],
                blocked_by=[],
                mitigates=[],
                mitigated_by=[],
                duplicates=[],
                duplicated_by=[],
                relates_to=[],
            )

        return TaskDetailResponse(
            id=task.id,
            workspace_id=task.workspace_id,
            created_by_id=task.created_by_id,
            title=task.title,
            status=task.status,
            priority=task.priority,
            seq=task.seq,
            public_id=f"{prefix}-{task.seq:03d}" if task.seq else f"{prefix}-000",
            description=task.description,
            assignee_id=task.assignee_id,
            project_id=task.project_id,
            team_id=task.team_id,
            due_at=task.due_at,
            is_blocked=task.is_blocked,
            blocked_reason=task.blocked_reason,
            created_at=task.created_at,
            updated_at=task.updated_at,
            relations=grouped,
        )

    async def create(self, request: CreateTaskRequest, requester: Principal) -> TaskResponse:
        # If an assignee is supplied, it must belong to the same workspace.
        if request.assignee_id is not None:
            assignee = await self.members.get_by_id(request.assignee_id)
            if assignee is None or assignee.workspace_id != requester.workspace_id:
                raise TaskNotFoundError("assignee not found")

        # Same-workspace check for project + team. We surface
        # ProjectNotFoundError / TeamNotFoundError on cross-tenant ids
        # rather than a generic TaskNotFoundError so the route can map
        # them precisely (and the agent's error log reads sensibly).
        if request.project_id is not None:
            await self._require_workspace_project(request.project_id, requester)
        if request.team_id is not None:
            await self._require_workspace_team(request.team_id, requester)

        # Atomic seq + prefix in one round-trip — rules out race-driven
        # collisions on the (workspace_id, seq) unique index.
        seq, prefix = await self.seq_allocator.allocate_next_task_seq(requester.workspace_id)

        now = datetime.utcnow()
        created = await self.tasks.create(
            Task(
                id=uuid4(),
                workspace_id=requester.workspace_id,
                created_by_id=requester.member_id,
                title=request.title,
                status=TaskStatus.PENDING,
                priority=request.priority,
                seq=seq,
                description=request.description,
                assignee_id=request.assignee_id,
                project_id=request.project_id,
                team_id=request.team_id,
                due_at=request.due_at,
                is_blocked=False,
                blocked_reason=None,
                created_at=now,
                updated_at=now,
            )
        )
        return TaskResponse.from_entity(created, prefix=prefix)

    async def update_links(
        self,
        task_id: UUID,
        request: UpdateTaskLinksRequest,
        requester: Principal,
    ) -> TaskResponse:
        """Move a task between projects and/or teams. Setting either to
        null explicitly clears it; omitting the field leaves it
        untouched (Pydantic's `model_fields_set` disambiguates)."""
        task = await self._load_task(task_id, requester)

        clear_project = "project_id" in request.model_fields_set and request.project_id is None
        clear_team = "team_id" in request.model_fields_set and request.team_id is None

        if request.project_id is not None and not clear_project:
            await self._require_workspace_project(request.project_id, requester)
        if request.team_id is not None and not clear_team:
            await self._require_workspace_team(request.team_id, requester)

        updated = await self.tasks.update_links(
            task.id,
            project_id=request.project_id if not clear_project else None,
            team_id=request.team_id if not clear_team else None,
            clear_project=clear_project,
            clear_team=clear_team,
        )
        prefix = await self._workspace_prefix(requester.workspace_id)
        return TaskResponse.from_entity(updated, prefix=prefix)

    async def _require_workspace_project(self, project_id: UUID, requester: Principal) -> None:
        if self.projects is None:  # pragma: no cover - DI invariant
            raise RuntimeError("project repo not wired")
        project = await self.projects.get_by_id(project_id)
        if project is None or project.workspace_id != requester.workspace_id:
            raise ProjectNotFoundError("project not found")

    async def _require_workspace_team(self, team_id: UUID, requester: Principal) -> None:
        if self.team_lookup is None:  # pragma: no cover - DI invariant
            raise RuntimeError("team repo not wired")
        team = await self.team_lookup.get_by_id(team_id)
        if team is None or team.workspace_id != requester.workspace_id:
            raise TeamNotFoundError("team not found")

    async def update_status(
        self,
        task_id: UUID,
        request: UpdateTaskStatusRequest,
        requester: Principal,
    ) -> TaskResponse:
        task = await self._load_task(task_id, requester)
        if request.status not in _ALLOWED_TRANSITIONS[task.status]:
            raise InvalidStatusTransitionError(
                f"cannot transition task from {task.status.value} to {request.status.value}"
            )

        updated = await self.tasks.update_status(
            task_id=task.id,
            status=request.status,
            tokens_used=request.tokens_used,
        )
        prefix = await self._workspace_prefix(requester.workspace_id)
        return TaskResponse.from_entity(updated, prefix=prefix)

    async def set_blocked(
        self,
        task_id: UUID,
        request: SetBlockedRequest,
        requester: Principal,
    ) -> TaskResponse:
        """Toggle the orthogonal blocked flag. The status is untouched —
        a blocked task can still be PENDING or IN_PROGRESS."""
        task = await self._load_task(task_id, requester)
        # When marking blocked, a reason is conventional. Empty string
        # is treated as None to keep the column tidy.
        reason = (request.reason or "").strip() or None if request.is_blocked else None
        updated = await self.tasks.set_blocked(
            task_id=task.id,
            is_blocked=request.is_blocked,
            blocked_reason=reason,
        )
        prefix = await self._workspace_prefix(requester.workspace_id)
        return TaskResponse.from_entity(updated, prefix=prefix)

    async def rate_task(
        self,
        task_id: UUID,
        request: RateTaskRequest,
        requester: Principal,
    ) -> TaskRatingResponse:
        """Issuer-only post-completion rating. Score backs the
        accuracy_percent stat on the assignee's agent dashboard."""
        if self.ratings is None:  # pragma: no cover - DI invariant
            raise RuntimeError("rate_task called without a ratings repository")

        task = await self._load_task(task_id, requester)

        if task.created_by_id != requester.member_id:
            raise RatingForbiddenError("only the task creator can rate the work")
        if task.status is not TaskStatus.DONE:
            raise TaskNotInDoneStateError("task must be DONE before it can be rated")
        if await self.ratings.get_for_task(task.id) is not None:
            raise TaskAlreadyRatedError("task already rated; ratings are single-shot")

        rating = await self.ratings.create(
            TaskRating(
                id=uuid4(),
                task_id=task.id,
                rated_by_id=requester.member_id,
                rated_member_id=task.assignee_id,
                score=request.score,
                feedback=request.feedback,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        )
        return TaskRatingResponse(
            task_id=rating.task_id,
            rated_by_id=rating.rated_by_id,
            rated_member_id=rating.rated_member_id,
            score=rating.score,
            feedback=rating.feedback,
            created_at=rating.created_at,
        )

    async def list_comments(self, task_id: UUID, requester: Principal) -> list[CommentResponse]:
        if self.comments is None:  # pragma: no cover - DI invariant
            raise RuntimeError("list_comments called without a comments repository")

        await self._load_task(task_id, requester)
        rows = await self.comments.list_for_task(task_id)
        return [await self._comment_to_response(row) for row in rows]

    async def post_comment(
        self,
        task_id: UUID,
        request: CreateCommentRequest,
        requester: Principal,
    ) -> CommentResponse:
        """Anyone in the workspace can comment — agents included. The
        author is whoever the JWT belongs to."""
        if self.comments is None:  # pragma: no cover - DI invariant
            raise RuntimeError("post_comment called without a comments repository")

        await self._load_task(task_id, requester)
        comment = await self.comments.create(
            TaskComment(
                id=uuid4(),
                task_id=task_id,
                author_member_id=requester.member_id,
                body=request.body,
            )
        )
        return await self._comment_to_response(comment)

    # ---------- relations ----------

    async def list_relations(self, task_id: UUID, requester: Principal) -> TaskRelationsResponse:
        if self.relations is None:  # pragma: no cover - DI invariant
            raise RuntimeError("list_relations called without a relations repository")

        await self._load_task(task_id, requester)
        rows = await self.relations.list_for_task(task_id)
        return await self._group_relations(task_id, rows, requester)

    async def create_relation(
        self,
        task_id: UUID,
        request: CreateRelationRequest,
        requester: Principal,
    ) -> TaskRelation:
        """Idempotent: returns the existing row if (source, target,
        type) is already linked. Same-workspace required, no self-link."""
        if self.relations is None:  # pragma: no cover - DI invariant
            raise RuntimeError("create_relation called without a relations repository")

        if task_id == request.target_task_id:
            raise TaskRelationSelfLinkError("a task cannot be linked to itself")

        # Both ends must be in the requester's workspace; both 404 the
        # same way as a missing task.
        await self._load_task(task_id, requester)
        await self._load_task(request.target_task_id, requester)

        existing = await self.relations.get_existing(
            source_task_id=task_id,
            target_task_id=request.target_task_id,
            relation_type=request.relation_type,
        )
        if existing is not None:
            raise TaskRelationAlreadyExistsError("this relation already exists between these tasks")

        return await self.relations.create(
            TaskRelation(
                id=uuid4(),
                source_task_id=task_id,
                target_task_id=request.target_task_id,
                relation_type=request.relation_type,
            )
        )

    async def delete_relation(self, task_id: UUID, relation_id: UUID, requester: Principal) -> None:
        """Removes the row by id. The route's task_id is taken as the
        owning task — we 404 if the relation isn't anchored to it."""
        if self.relations is None:  # pragma: no cover - DI invariant
            raise RuntimeError("delete_relation called without a relations repository")

        relation = await self.relations.get_by_id(relation_id)
        if relation is None:
            raise TaskRelationNotFoundError("relation not found")
        if task_id not in (relation.source_task_id, relation.target_task_id):
            raise TaskRelationNotFoundError("relation not found")
        # Tenant-isolation: the route already loaded the task to confirm
        # the requester has access; we trust task_id here.
        await self._load_task(task_id, requester)
        await self.relations.delete(relation_id)

    async def _group_relations(
        self,
        task_id: UUID,
        rows: list[TaskRelation],
        requester: Principal,
    ) -> TaskRelationsResponse:
        # Bulk-fetch the counterpart tasks in one round-trip so the UI
        # can render public_id + title without N additional GETs.
        counterpart_ids = {
            r.target_task_id if r.source_task_id == task_id else r.source_task_id for r in rows
        }
        tasks_by_id: dict[UUID, Task] = {}
        if counterpart_ids:
            for task in await self.tasks.list_by_ids(list(counterpart_ids)):
                # Defensive: only surface counterpart tasks in the same
                # workspace. Cross-workspace shouldn't be possible
                # because creation rejects it, but DB-level FKs don't
                # enforce tenancy so we double-check here.
                if task.workspace_id == requester.workspace_id:
                    tasks_by_id[task.id] = task

        prefix = await self._workspace_prefix(requester.workspace_id)

        def to_item(relation: TaskRelation, counterpart_id: UUID) -> RelationItem | None:
            counterpart = tasks_by_id.get(counterpart_id)
            if counterpart is None:
                return None
            return RelationItem(
                relation_id=relation.id,
                task_id=counterpart.id,
                public_id=f"{prefix}-{counterpart.seq:03d}",
                title=counterpart.title,
                status=counterpart.status,
                is_blocked=counterpart.is_blocked,
            )

        groups: dict[str, list[RelationItem]] = {
            "blocks": [],
            "blocked_by": [],
            "mitigates": [],
            "mitigated_by": [],
            "duplicates": [],
            "duplicated_by": [],
            "relates_to": [],
        }

        for r in rows:
            outgoing = r.source_task_id == task_id
            counterpart_id = r.target_task_id if outgoing else r.source_task_id
            item = to_item(r, counterpart_id)
            if item is None:
                continue

            if r.relation_type is TaskRelationType.RELATES_TO:
                # Symmetric — the same row appears in `relates_to` for
                # both ends; don't double-bucket.
                groups["relates_to"].append(item)
                continue

            if r.relation_type is TaskRelationType.BLOCKS:
                (groups["blocks"] if outgoing else groups["blocked_by"]).append(item)
            elif r.relation_type is TaskRelationType.MITIGATES:
                (groups["mitigates"] if outgoing else groups["mitigated_by"]).append(item)
            elif r.relation_type is TaskRelationType.DUPLICATES:
                (groups["duplicates"] if outgoing else groups["duplicated_by"]).append(item)

        return TaskRelationsResponse(**groups)

    async def _comment_to_response(self, comment: TaskComment) -> CommentResponse:
        author_name: str | None = None
        if comment.author_member_id is not None:
            # Best-effort name lookup. `members` is the auth-shape repo
            # so this is a single primary-key fetch per comment. Lists
            # of comments are paginated in practice; for now they're
            # rendered in full.
            author = await self.members.get_by_id(comment.author_member_id)
            author_name = author.name if author is not None else None
        return CommentResponse(
            id=comment.id,
            task_id=comment.task_id,
            author_member_id=comment.author_member_id,
            author_name=author_name,
            body=comment.body,
            created_at=comment.created_at,
        )

    async def _load_task(self, task_id: UUID, requester: Principal) -> Task:
        task = await self.tasks.get_by_id(task_id)
        if task is None or task.workspace_id != requester.workspace_id:
            raise TaskNotFoundError("task not found")
        return task

    async def _load_target(self, member_id: UUID, requester: Principal) -> Member:
        target = await self.members.get_by_id(member_id)
        if target is None or target.workspace_id != requester.workspace_id:
            raise TaskNotFoundError("assignee not found")
        return target

    async def _workspace_prefix(self, workspace_id: UUID) -> str:
        ws = await self.workspaces.get_by_id(workspace_id)
        if ws is None:  # pragma: no cover - tenant invariant
            raise TaskNotFoundError("workspace not found")
        return ws.task_prefix

    @staticmethod
    def _enforce_hierarchy(requester: Principal, target: Member) -> None:
        # Lower numerical priority = higher rank. A requester may only delegate
        # to members with a strictly greater numerical priority (lower rank).
        if requester.priority >= target.priority:
            raise DelegationForbiddenError(
                "requester rank is not high enough to delegate to this member"
            )
