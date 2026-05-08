from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.entities import AgentStats, Member


class CreateAgentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    # Numerical priority — lower = higher rank. Owner is 1; agents typically
    # sit at 5+ so humans (priority 1-4) can delegate to them but agents
    # cannot delegate up. Capped at 100 to keep the hierarchy coherent.
    priority: int = Field(default=5, ge=2, le=100)
    # Free-form model identifier ("claude-opus-4-7", "gpt-5", etc.). Pure
    # informational; lets users see at a glance which underlying model an
    # agent runs on.
    model: str | None = Field(default=None, max_length=120)


class UpdateAgentRequest(BaseModel):
    """Partial update — fields not present in the body are left untouched.
    `id` is immutable. Setting `model` to null explicitly clears it; omit
    the field to leave it unchanged."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    priority: int | None = Field(default=None, ge=2, le=100)
    model: str | None = Field(default=None, max_length=120)


class AgentResponse(BaseModel):
    """Safe shape (no API key, no stats). Returned by GET /agents."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    name: str
    priority: int
    model: str | None
    created_at: datetime

    @classmethod
    def from_entity(cls, member: Member) -> AgentResponse:
        return cls(
            id=member.id,
            workspace_id=member.workspace_id,
            name=member.name,
            priority=member.priority,
            model=member.model,
            created_at=member.created_at,
        )


class CreateAgentResponse(BaseModel):
    """Returned exactly once on POST /agents with the raw API key in plaintext.
    Subsequent GETs return AgentResponse only — the secret is bcrypted on
    persist and we cannot recover it."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    name: str
    priority: int
    model: str | None
    api_key: str


class AgentStatsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    assigned_count: int
    completed_count: int
    avg_resolution_seconds: float | None
    accuracy_percent: float | None
    last_activity_at: datetime | None
    total_tokens_used: int

    @classmethod
    def from_entity(cls, stats: AgentStats) -> AgentStatsResponse:
        return cls(
            assigned_count=stats.assigned_count,
            completed_count=stats.completed_count,
            avg_resolution_seconds=stats.avg_resolution_seconds,
            accuracy_percent=stats.accuracy_percent,
            last_activity_at=stats.last_activity_at,
            total_tokens_used=stats.total_tokens_used,
        )


class AgentDetailResponse(BaseModel):
    """The agent detail page reads this. Bundles the safe agent shape
    with computed stats so the UI doesn't need a second round-trip."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    name: str
    priority: int
    model: str | None
    created_at: datetime
    stats: AgentStatsResponse
