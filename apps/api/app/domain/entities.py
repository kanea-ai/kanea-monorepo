from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from app.domain.enums import MemberRole, MemberType, OAuthProvider, TaskStatus


@dataclass(slots=True)
class Workspace:
    id: UUID
    name: str
    slug: str
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
    description: str | None = None
    assignee_id: UUID | None = None
    due_at: datetime | None = None
    blocked_reason: str | None = None
    completed_at: datetime | None = None
    # Running total of LLM tokens an agent has spent on this task. Agents
    # report it back through the status-update endpoint so it accumulates
    # across iterations.
    tokens_used: int = 0
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
