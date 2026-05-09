from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from app.application.auth.ports import MemberRepository
from app.application.tasks.ports import (
    TaskCommentRepository,
    TaskRatingRepository,
    TaskRepository,
    WorkspaceTaskSeqRepository,
)
from app.application.tasks.schemas import (
    CommentResponse,
    CreateCommentRequest,
    CreateTaskRequest,
    DelegateTaskRequest,
    Principal,
    RateTaskRequest,
    SetBlockedRequest,
    TaskRatingResponse,
    TaskResponse,
    UpdateTaskStatusRequest,
)
from app.application.tenants.ports import WorkspaceReadRepository
from app.domain.entities import Member, Task, TaskComment, TaskRating
from app.domain.enums import TaskStatus
from app.domain.exceptions import (
    DelegationForbiddenError,
    InvalidStatusTransitionError,
    RatingForbiddenError,
    TaskAlreadyRatedError,
    TaskNotFoundError,
    TaskNotInDoneStateError,
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
    ) -> list[TaskResponse]:
        rows = await self.tasks.list_by_workspace(
            requester.workspace_id, status=status, blocked_only=blocked_only
        )
        prefix = await self._workspace_prefix(requester.workspace_id)
        return [TaskResponse.from_entity(row, prefix=prefix) for row in rows]

    async def get_by_id(self, task_id: UUID, requester: Principal) -> TaskResponse:
        task = await self._load_task(task_id, requester)
        prefix = await self._workspace_prefix(requester.workspace_id)
        return TaskResponse.from_entity(task, prefix=prefix)

    async def create(self, request: CreateTaskRequest, requester: Principal) -> TaskResponse:
        # If an assignee is supplied, it must belong to the same workspace.
        if request.assignee_id is not None:
            assignee = await self.members.get_by_id(request.assignee_id)
            if assignee is None or assignee.workspace_id != requester.workspace_id:
                raise TaskNotFoundError("assignee not found")

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
                due_at=request.due_at,
                is_blocked=False,
                blocked_reason=None,
                created_at=now,
                updated_at=now,
            )
        )
        return TaskResponse.from_entity(created, prefix=prefix)

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
