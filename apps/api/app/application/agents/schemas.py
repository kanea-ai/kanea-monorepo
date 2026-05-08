from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.entities import Member


class CreateAgentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    # Numerical priority — lower = higher rank. Owner is 1; agents typically
    # sit at 5+ so humans (priority 1-4) can delegate to them but agents
    # cannot delegate up. Capped at 100 to keep the hierarchy coherent.
    priority: int = Field(default=5, ge=2, le=100)


class AgentResponse(BaseModel):
    """The 'safe' shape — never includes the API key. Returned by GET /agents
    and listed on the team page."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    name: str
    priority: int
    created_at: datetime

    @classmethod
    def from_entity(cls, member: Member) -> AgentResponse:
        return cls(
            id=member.id,
            workspace_id=member.workspace_id,
            name=member.name,
            priority=member.priority,
            created_at=member.created_at,
        )


class CreateAgentResponse(BaseModel):
    """Returned exactly once on POST /agents with the raw API key in plaintext.
    Subsequent GETs return the safe AgentResponse only — the secret is
    bcrypted on persist and we cannot recover it."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    name: str
    priority: int
    # The plaintext API key. The agent uses (id, api_key) at
    # POST /api/v1/auth/agent-token to exchange for a JWT.
    api_key: str
