from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.entities import Team


class CreateTeamRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)


class UpdateTeamRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)


class TeamResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    name: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_entity(cls, team: Team) -> TeamResponse:
        return cls(
            id=team.id,
            workspace_id=team.workspace_id,
            name=team.name,
            created_at=team.created_at,
            updated_at=team.updated_at,
        )
