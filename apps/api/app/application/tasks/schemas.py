from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.entities import Task
from app.domain.enums import MemberRole, MemberType, TaskStatus


@dataclass(slots=True, frozen=True)
class Principal:
    """Caller identity decoded from a verified JWT.

    `priority` is the numerical rank claim — lower means higher rank
    (CEO = 1, Agent = 5). `role` is the workspace role used for RBAC
    on tenant operations (invites, member management). Stored on the
    principal so checks don't need to hit the database for every
    request.
    """

    member_id: UUID
    workspace_id: UUID
    type: MemberType
    priority: int
    scope: str
    role: MemberRole = MemberRole.MEMBER


class DelegateTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    member_id: UUID


class UpdateTaskStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: TaskStatus
    blocked_reason: str | None = None


class CreateTaskRequest(BaseModel):
    """Inputs accepted on POST /tasks. workspace_id and created_by_id are
    derived from the authenticated principal — not user-supplied — so a
    member can never create a task in a workspace they don't belong to."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=20_000)
    priority: int = Field(default=0, ge=0, le=1000)
    assignee_id: UUID | None = None
    due_at: datetime | None = None


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    created_by_id: UUID
    title: str
    status: TaskStatus
    priority: int
    description: str | None
    assignee_id: UUID | None
    due_at: datetime | None
    blocked_reason: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_entity(cls, task: Task) -> TaskResponse:
        return cls(
            id=task.id,
            workspace_id=task.workspace_id,
            created_by_id=task.created_by_id,
            title=task.title,
            status=task.status,
            priority=task.priority,
            description=task.description,
            assignee_id=task.assignee_id,
            due_at=task.due_at,
            blocked_reason=task.blocked_reason,
            created_at=task.created_at,
            updated_at=task.updated_at,
        )
