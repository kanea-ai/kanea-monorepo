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
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
