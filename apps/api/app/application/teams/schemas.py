from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.entities import Team


class CreateTeamRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=20_000)
    department_id: UUID | None = None


class UpdateTeamRequest(BaseModel):
    """Partial update — fields not present in the body stay as-is.
    Setting ``description`` or ``department_id`` to null explicitly
    clears them; omit the field to leave it untouched."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=20_000)
    department_id: UUID | None = None


class TeamResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    name: str
    description: str | None
    department_id: UUID | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_entity(cls, team: Team) -> TeamResponse:
        return cls(
            id=team.id,
            workspace_id=team.workspace_id,
            name=team.name,
            description=team.description,
            department_id=team.department_id,
            created_at=team.created_at,
            updated_at=team.updated_at,
        )
