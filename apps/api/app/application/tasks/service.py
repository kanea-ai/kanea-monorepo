from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from app.application.auth.ports import MemberRepository
from app.application.tasks.ports import TaskRatingRepository, TaskRepository
from app.application.tasks.schemas import (
    CreateTaskRequest,
    DelegateTaskRequest,
    Principal,
    RateTaskRequest,
    TaskRatingResponse,
    TaskResponse,
    UpdateTaskStatusRequest,
)
from app.domain.entities import Member, Task, TaskRating
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
# BLOCKED -> IN_PROGRESS is the human "Resolve" path from the Exception Queue.
_ALLOWED_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.PENDING: frozenset({TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED}),
    TaskStatus.IN_PROGRESS: frozenset({TaskStatus.BLOCKED, TaskStatus.DONE, TaskStatus.CANCELLED}),
    TaskStatus.BLOCKED: frozenset({TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED}),
    TaskStatus.DONE: frozenset(),
    TaskStatus.CANCELLED: frozenset(),
}


@dataclass(slots=True)
class TaskService:
    tasks: TaskRepository
    members: MemberRepository
    # Optional so existing call-sites that don't construct ratings (tests,
    # legacy DI paths) keep working. The rate_task() entry-point checks
    # for None and raises a clear error if it's invoked without one.
    ratings: TaskRatingRepository | None = None

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
        return TaskResponse.from_entity(updated)

    async def list_for_workspace(
        self,
        requester: Principal,
        *,
        status: TaskStatus | None = None,
    ) -> list[TaskResponse]:
        rows = await self.tasks.list_by_workspace(requester.workspace_id, status=status)
        return [TaskResponse.from_entity(row) for row in rows]

    async def get_by_id(self, task_id: UUID, requester: Principal) -> TaskResponse:
        task = await self._load_task(task_id, requester)
        return TaskResponse.from_entity(task)

    async def create(self, request: CreateTaskRequest, requester: Principal) -> TaskResponse:
        # If an assignee is supplied, it must belong to the same workspace.
        # The hierarchy rule (only delegate down) is enforced for explicit
        # delegation; on initial create we allow any same-workspace member
        # to be the first assignee — including yourself, including agents.
        if request.assignee_id is not None:
            assignee = await self.members.get_by_id(request.assignee_id)
            if assignee is None or assignee.workspace_id != requester.workspace_id:
                raise TaskNotFoundError("assignee not found")

        now = datetime.utcnow()
        created = await self.tasks.create(
            Task(
                id=uuid4(),
                workspace_id=requester.workspace_id,
                created_by_id=requester.member_id,
                title=request.title,
                status=TaskStatus.PENDING,
                priority=request.priority,
                description=request.description,
                assignee_id=request.assignee_id,
                due_at=request.due_at,
                blocked_reason=None,
                created_at=now,
                updated_at=now,
            )
        )
        return TaskResponse.from_entity(created)

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

        # Resolving from BLOCKED clears the reason; setting BLOCKED stores it.
        blocked_reason = request.blocked_reason if request.status is TaskStatus.BLOCKED else None
        updated = await self.tasks.update_status(
            task_id=task.id,
            status=request.status,
            blocked_reason=blocked_reason,
            tokens_used=request.tokens_used,
        )
        return TaskResponse.from_entity(updated)

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
            # Only the issuer rates. Assignees can't self-rate.
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

    @staticmethod
    def _enforce_hierarchy(requester: Principal, target: Member) -> None:
        # Lower numerical priority = higher rank. A requester may only delegate
        # to members with a strictly greater numerical priority (lower rank).
        if requester.priority >= target.priority:
            raise DelegationForbiddenError(
                "requester rank is not high enough to delegate to this member"
            )
