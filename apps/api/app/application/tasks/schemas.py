from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.entities import Task
from app.domain.enums import (
    MemberRole,
    MemberType,
    TaskActivityType,
    TaskRelationType,
    TaskStatus,
)


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
    # Cumulative tokens spent on the task so far. Agents bump this when
    # they mark DONE (or any other transition) so the workspace can see
    # how expensive each task was. Optional — omit to leave the value
    # alone.
    tokens_used: int | None = Field(default=None, ge=0)


class SetBlockedRequest(BaseModel):
    """Toggle the orthogonal `is_blocked` flag. `reason` is required when
    blocking, ignored when unblocking."""

    model_config = ConfigDict(extra="forbid")

    is_blocked: bool
    reason: str | None = Field(default=None, max_length=2_000)


class RateTaskRequest(BaseModel):
    """Issuer's rating of the assignee's work on a DONE task. score is a
    0-100 percentage capturing the work's quality, supervision required,
    loops, and other subjective factors. feedback is optional free-form
    context for future fine-tuning."""

    model_config = ConfigDict(extra="forbid")

    score: int = Field(ge=0, le=100)
    feedback: str | None = Field(default=None, max_length=10_000)


class TaskRatingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    task_id: UUID
    rated_by_id: UUID
    rated_member_id: UUID | None
    score: int
    feedback: str | None
    created_at: datetime


class CreateTaskRequest(BaseModel):
    """Inputs accepted on POST /tasks. workspace_id and created_by_id are
    derived from the authenticated principal — not user-supplied — so a
    member can never create a task in a workspace they don't belong to."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=20_000)
    priority: int = Field(default=0, ge=0, le=1000)
    assignee_id: UUID | None = None
    project_id: UUID | None = None
    team_id: UUID | None = None
    due_at: datetime | None = None


class UpdateTaskLinksRequest(BaseModel):
    """Move a task between projects / teams. Setting either to null
    explicitly clears it; omitting the field leaves it untouched."""

    model_config = ConfigDict(extra="forbid")

    project_id: UUID | None = None
    team_id: UUID | None = None


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    created_by_id: UUID
    title: str
    status: TaskStatus
    priority: int
    seq: int
    # Human-readable id like ``DEVOPS-001``. Built by the service layer
    # from the workspace prefix + zero-padded seq. Stable for the life
    # of the task; not used as a primary key.
    public_id: str
    description: str | None
    assignee_id: UUID | None
    project_id: UUID | None
    team_id: UUID | None
    due_at: datetime | None
    is_blocked: bool
    blocked_reason: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_entity(cls, task: Task, *, prefix: str) -> TaskResponse:
        return cls(
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
        )


class CreateRelationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relation_type: TaskRelationType
    target_task_id: UUID


class RelationItem(BaseModel):
    """One related task as the UI sees it. ``relation_id`` is the row
    id (used to delete), ``task_id`` and ``public_id`` identify the
    counterpart task."""

    model_config = ConfigDict(from_attributes=True)

    relation_id: UUID
    task_id: UUID
    public_id: str
    title: str
    status: TaskStatus
    is_blocked: bool


class TaskRelationsResponse(BaseModel):
    """Seven UI buckets. ``relates_to`` collapses both directions of
    the symmetric RELATES_TO type into one list."""

    blocks: list[RelationItem]
    blocked_by: list[RelationItem]
    mitigates: list[RelationItem]
    mitigated_by: list[RelationItem]
    duplicates: list[RelationItem]
    duplicated_by: list[RelationItem]
    relates_to: list[RelationItem]


class TaskDetailResponse(BaseModel):
    """Returned by GET /tasks/{id}. Mirrors TaskResponse and adds the
    seven relation buckets so an agent that fetches one task gets the
    complete picture of its linked work in a single round-trip — no
    second call to /relations required."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    created_by_id: UUID
    title: str
    status: TaskStatus
    priority: int
    seq: int
    public_id: str
    description: str | None
    assignee_id: UUID | None
    due_at: datetime | None
    project_id: UUID | None
    team_id: UUID | None
    is_blocked: bool
    blocked_reason: str | None
    created_at: datetime
    updated_at: datetime
    relations: TaskRelationsResponse


class ActivityResponse(BaseModel):
    """One row of a task's audit log. The agent reads this to
    reconstruct what happened on a task — status flips, blocks, moves,
    ratings — and pair it with comments for the full story."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID
    actor_member_id: UUID | None
    actor_name: str | None
    event_type: TaskActivityType
    # JSON payload, shape-per-event (see TaskActivityType docstring).
    payload: dict
    created_at: datetime


class CreateCommentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1, max_length=20_000)


class CommentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID
    author_member_id: UUID | None
    # Display name resolved at read time so the UI doesn't need a
    # second round-trip. Null only when the author was deleted.
    author_name: str | None
    body: str
    created_at: datetime
