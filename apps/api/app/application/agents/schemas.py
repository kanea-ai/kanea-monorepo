from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.entities import AgentApiKey, AgentStats, Member


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
    """Safe shape (no API key, no stats). Returned by GET /agents.

    Includes last_seen_at + health_status so the list page can render
    the presence pill and run the status filter without an N+1 detail
    fetch per row."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    name: str
    priority: int
    model: str | None
    created_at: datetime
    last_seen_at: datetime | None
    health_status: str

    @classmethod
    def from_entity(cls, member: Member) -> AgentResponse:
        # Local import to avoid a circular schemas <-> service edge.
        from app.application.agents.service import derive_health_status

        return cls(
            id=member.id,
            workspace_id=member.workspace_id,
            name=member.name,
            priority=member.priority,
            model=member.model,
            created_at=member.created_at,
            last_seen_at=member.last_seen_at,
            health_status=derive_health_status(member.last_seen_at),
        )


class CreateAgentResponse(BaseModel):
    """Returned exactly once on POST /agents with the raw API key in
    plaintext. Subsequent GETs return AgentResponse only — only the
    HMAC-SHA-256 digest of the key body is persisted, so the plaintext
    cannot be recovered."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    name: str
    priority: int
    model: str | None
    api_key: str


class IssueAgentApiKeyRequest(BaseModel):
    """Body for ``POST /agents/{id}/api-keys``. ``label`` is optional
    human-readable context the operator can set so future inventory
    reads ("ci-runner key minted by Bob") stay meaningful."""

    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(default=None, min_length=1, max_length=80)


class AgentApiKeyResponse(BaseModel):
    """Listing shape — metadata only. No plaintext, no hash. ``prefix``
    + ``last4`` form the fingerprint the UI shows ("kna_live_…AbCd").
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    prefix: str
    last4: str
    label: str | None
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None

    @classmethod
    def from_entity(cls, key: AgentApiKey) -> AgentApiKeyResponse:
        return cls(
            id=key.id,
            prefix=key.prefix,
            last4=key.last4,
            label=key.label,
            created_at=key.created_at,
            last_used_at=key.last_used_at,
            revoked_at=key.revoked_at,
        )


class IssueAgentApiKeyResponse(BaseModel):
    """Returned exactly once on ``POST /agents/{id}/api-keys`` with the
    plaintext key. Same shape as ``AgentApiKeyResponse`` plus the
    ``api_key`` field — the route returns this, the listing endpoint
    returns ``AgentApiKeyResponse``."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    prefix: str
    last4: str
    label: str | None
    created_at: datetime
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
    # Most recent contact from the agent. Null until the agent calls
    # /api/v1/auth/agent-token at least once. Surfaces as a health pill
    # in the UI: ONLINE (≤5min) / IDLE (≤1h) / STALE (>1h or never).
    last_seen_at: datetime | None
    health_status: str
    stats: AgentStatsResponse
