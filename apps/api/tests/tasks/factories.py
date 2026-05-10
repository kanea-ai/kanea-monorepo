from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.application.tasks.schemas import Principal
from app.domain.entities import Task
from app.domain.enums import MemberRole, MemberType, TaskStatus


def make_principal(
    *,
    member_id: UUID | None = None,
    workspace_id: UUID | None = None,
    member_type: MemberType = MemberType.HUMAN,
    priority: int = 1,
    scope: str = "human",
    # Default to OWNER so existing service-level tests (which pre-date
    # the board-level RBAC in section 2) keep their full visibility on
    # /tasks list calls. Tests that need to exercise non-admin scoping
    # pass role=MemberRole.WORKSPACE_USER explicitly.
    role: MemberRole = MemberRole.WORKSPACE_OWNER,
) -> Principal:
    return Principal(
        member_id=member_id or uuid4(),
        workspace_id=workspace_id or uuid4(),
        type=member_type,
        priority=priority,
        scope=scope,
        role=role,
    )


def make_task(
    *,
    task_id: UUID | None = None,
    workspace_id: UUID | None = None,
    created_by_id: UUID | None = None,
    assignee_id: UUID | None = None,
    team_id: UUID | None = None,
    title: str = "Investigate latency spike",
    status: TaskStatus = TaskStatus.PENDING,
    priority: int = 3,
    seq: int = 1,
    is_blocked: bool = False,
    blocked_reason: str | None = None,
) -> Task:
    now = datetime.now(UTC)
    return Task(
        id=task_id or uuid4(),
        workspace_id=workspace_id or uuid4(),
        created_by_id=created_by_id or uuid4(),
        title=title,
        status=status,
        priority=priority,
        seq=seq,
        description=None,
        assignee_id=assignee_id,
        team_id=team_id,
        due_at=None,
        is_blocked=is_blocked,
        blocked_reason=blocked_reason,
        created_at=now,
        updated_at=now,
    )
