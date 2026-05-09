from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from app.domain.enums import (
    MemberRole,
    MemberType,
    OAuthProvider,
    ProjectStatus,
    TaskActivityType,
    TaskRelationType,
    TaskStatus,
)


@dataclass(slots=True)
class Workspace:
    id: UUID
    name: str
    slug: str
    # Short alpha prefix for human-readable task ids ("DEVOPS" -> DEVOPS-001).
    # Always uppercase, derived from `name` on signup, capped at 8 chars.
    task_prefix: str
    # Monotonic counter incremented atomically when a task is created.
    # Always points at the *next* seq to hand out.
    next_task_seq: int
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class Team:
    id: UUID
    workspace_id: UUID
    name: str
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class Project:
    """Workspace-scoped goal. A Project groups Tasks toward a single
    objective; tasks across the same Project can sit on different
    Teams. Status flips between ACTIVE and ARCHIVED — archive hides
    the project from default lists without deleting its tasks."""

    id: UUID
    workspace_id: UUID
    name: str
    status: ProjectStatus
    description: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(slots=True)
class Member:
    id: UUID
    workspace_id: UUID
    type: MemberType
    name: str
    priority: int
    team_id: UUID | None = None
    email: str | None = None
    role: MemberRole = MemberRole.MEMBER
    # Underlying LLM model identifier for AGENT-typed members. Free-form
    # so the user can label however they want ("claude-opus-4-7", "gpt-5",
    # "Custom: agent-pipeline-v2", etc.). Null on humans.
    model: str | None = None
    # Last time this member touched the api — stamped on agent JWT
    # issuance and on POST /api/v1/agents/me/heartbeat. Drives the
    # derived health_status pill on the agent detail view. Null on
    # humans (we only surface it for agents).
    last_seen_at: datetime | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def is_human(self) -> bool:
        return self.type is MemberType.HUMAN

    @property
    def is_agent(self) -> bool:
        return self.type is MemberType.AGENT

    @property
    def can_invite(self) -> bool:
        """OWNER and ADMIN can invite; MEMBER cannot. Same shape applies
        to most workspace-management actions."""
        return self.role in (MemberRole.OWNER, MemberRole.ADMIN)


@dataclass(slots=True)
class Credentials:
    id: UUID
    member_id: UUID
    password_hash: str | None
    agent_secret_hash: str | None
    created_at: datetime
    updated_at: datetime
    # OAuth identity. (provider, oauth_id) is globally unique — see
    # uq_credentials_oauth_provider_oauth_id in migration 0003.
    oauth_provider: OAuthProvider | None = None
    oauth_id: str | None = None


@dataclass(slots=True)
class Invite:
    id: UUID
    workspace_id: UUID
    invited_by_id: UUID
    email: str
    role: MemberRole
    # SHA-256 hex of the raw token. Plaintext token is returned to the
    # inviter exactly once; lookups are by hash.
    token_hash: str
    expires_at: datetime
    accepted_at: datetime | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(slots=True)
class Task:
    id: UUID
    workspace_id: UUID
    created_by_id: UUID
    title: str
    status: TaskStatus
    priority: int
    # Per-workspace integer. Combined with the workspace task_prefix it
    # produces a human-readable id like ``DEVOPS-001``. Allocated at
    # creation via an atomic UPDATE ... RETURNING on the workspace row.
    seq: int = 0
    description: str | None = None
    assignee_id: UUID | None = None
    # Optional links into the Workspace -> Project -> Task -> Team
    # hierarchy. Both nullable: a backlog task lives without a project,
    # an unowned task can live without a team. SET NULL on cascade so
    # deleting a project/team doesn't orphan the task itself.
    project_id: UUID | None = None
    team_id: UUID | None = None
    due_at: datetime | None = None
    # Blocked-flag is orthogonal to status. A task can be IN_PROGRESS
    # and blocked at the same time. blocked_reason is only meaningful
    # when is_blocked is true.
    is_blocked: bool = False
    blocked_reason: str | None = None
    completed_at: datetime | None = None
    # Running total of LLM tokens an agent has spent on this task. Agents
    # report it back through the status-update endpoint so it accumulates
    # across iterations.
    tokens_used: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(slots=True)
class TaskRelation:
    """One directed link between two tasks. Lives in its own table so
    relations can be added/removed without touching the task rows."""

    id: UUID
    source_task_id: UUID
    target_task_id: UUID
    relation_type: TaskRelationType
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(slots=True)
class TaskActivity:
    """One row of the append-only audit log on a task. The actor is
    null after the member is deleted — the event still survives so the
    agent can trace what happened."""

    id: UUID
    task_id: UUID
    actor_member_id: UUID | None
    event_type: TaskActivityType
    # Free-form JSON payload — see TaskActivityType docstring for the
    # per-event shape.
    payload: dict
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(slots=True)
class TaskComment:
    """One line of a task's discussion thread. Authors can be human or
    agent members; `author_member_id` is null after the author is
    deleted (FK SET NULL) so threads stay legible."""

    id: UUID
    task_id: UUID
    author_member_id: UUID | None
    body: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(slots=True)
class TaskRating:
    """A 0-100 score the issue creator leaves for the assignee after a
    task lands in DONE. One rating per task (the primary key constraint
    enforces it). Drives `accuracy_percent` on agent stats."""

    id: UUID
    task_id: UUID
    rated_by_id: UUID
    rated_member_id: UUID | None  # null after the rated member is deleted
    score: int  # 0-100, validated at the schema layer
    feedback: str | None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(slots=True, frozen=True)
class AgentStats:
    """Materialised at request time from queries against tasks +
    task_ratings. Computed in one or two SQL aggregations rather than
    Python-side iteration so it scales to workspaces with thousands of
    tasks."""

    assigned_count: int
    completed_count: int
    avg_resolution_seconds: float | None
    accuracy_percent: float | None
    last_activity_at: datetime | None
    total_tokens_used: int
