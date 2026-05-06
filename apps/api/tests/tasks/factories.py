from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.application.tasks.schemas import Principal
from app.domain.entities import Task
from app.domain.enums import MemberType, TaskStatus


def make_principal(
    *,
    member_id: UUID | None = None,
    workspace_id: UUID | None = None,
    member_type: MemberType = MemberType.HUMAN,
    priority: int = 1,
    scope: str = "human",
) -> Principal:
    return Principal(
        member_id=member_id or uuid4(),
        workspace_id=workspace_id or uuid4(),
        type=member_type,
        priority=priority,
        scope=scope,
    )


def make_task(
    *,
    task_id: UUID | None = None,
    workspace_id: UUID | None = None,
    created_by_id: UUID | None = None,
    assignee_id: UUID | None = None,
    title: str = "Investigate latency spike",
    status: TaskStatus = TaskStatus.PENDING,
    priority: int = 3,
) -> Task:
    now = datetime.now(UTC)
    return Task(
        id=task_id or uuid4(),
        workspace_id=workspace_id or uuid4(),
        created_by_id=created_by_id or uuid4(),
        title=title,
        status=status,
        priority=priority,
        description=None,
        assignee_id=assignee_id,
        due_at=None,
        created_at=now,
        updated_at=now,
    )
