from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.application.auth.ports import MemberRepository
from app.application.tasks.ports import TaskRepository
from app.application.tasks.schemas import (
    DelegateTaskRequest,
    Principal,
    TaskResponse,
    UpdateTaskStatusRequest,
)
from app.domain.entities import Member, Task
from app.domain.enums import TaskStatus
from app.domain.exceptions import (
    DelegationForbiddenError,
    InvalidStatusTransitionError,
    TaskNotFoundError,
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
        )
        return TaskResponse.from_entity(updated)

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
