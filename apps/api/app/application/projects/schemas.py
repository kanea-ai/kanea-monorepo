from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.application.tasks.schemas import (
    ActivityResponse,
    CommentResponse,
    TaskRatingResponse,
)
from app.domain.entities import Project
from app.domain.enums import ProjectStatus, TaskStatus


class CreateProjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=20_000)


class UpdateProjectRequest(BaseModel):
    """Partial update — fields not present in the body stay as-is.
    Setting ``description`` to null explicitly clears it; omit the field
    to leave it untouched."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=20_000)
    status: ProjectStatus | None = None


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    name: str
    description: str | None
    status: ProjectStatus
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_entity(cls, project: Project) -> ProjectResponse:
        return cls(
            id=project.id,
            workspace_id=project.workspace_id,
            name=project.name,
            description=project.description,
            status=project.status,
            created_at=project.created_at,
            updated_at=project.updated_at,
        )


# ---------- AI-facing history bundle ----------


class ProjectHistorySummary(BaseModel):
    """Per-project rollups so the agent can spot trends without
    re-aggregating raw rows."""

    total_tasks: int
    by_status: dict[str, int]
    blocked_now: int
    avg_resolution_seconds: float | None
    total_tokens_used: int
    rated_count: int
    avg_rating: float | None


class ProjectTaskHistory(BaseModel):
    """Per-task slice — task metadata, its full audit log, comment
    thread, and (optional) issuer rating. The agent reads this to
    reason about what went right/wrong on each piece of work."""

    id: UUID
    public_id: str
    title: str
    status: TaskStatus
    is_blocked: bool
    blocked_reason: str | None
    description: str | None
    priority: int
    assignee_id: UUID | None
    project_id: UUID | None
    team_id: UUID | None
    tokens_used: int
    created_at: datetime
    completed_at: datetime | None
    rating: TaskRatingResponse | None
    activities: list[ActivityResponse]
    comments: list[CommentResponse]


class ProjectHistoryResponse(BaseModel):
    """Single-shot bundle for the agent to analyse a project. Avoids
    N round-trips: project metadata + summary + per-task history with
    activities + comments + ratings, all in one fetch."""

    project: ProjectResponse
    summary: ProjectHistorySummary
    tasks: list[ProjectTaskHistory]
