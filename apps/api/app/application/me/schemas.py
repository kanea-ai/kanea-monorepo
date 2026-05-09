from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import MemberRole, MemberType, OAuthProvider, TeamRole


class MeProfileResponse(BaseModel):
    """Combined view of who the principal is right now: the global User
    row + the active workspace membership. Drives the /profile page and
    the header avatar menu."""

    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    email: str
    full_name: str
    has_password: bool
    oauth_provider: OAuthProvider | None

    member_id: UUID
    workspace_id: UUID
    workspace_name: str
    role: MemberRole
    type: MemberType
    team_id: UUID | None
    team_role: TeamRole | None


class UpdateMeRequest(BaseModel):
    """Self-edit; only the User-side display name is mutable here. The
    per-workspace `Member.name` follows the User unless an admin
    overrides it via /tenants/members/{id}."""

    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(min_length=1, max_length=120)


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=256)


class MeStatsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    assigned_count: int
    completed_count: int
    avg_resolution_seconds: float | None
    last_activity_at: datetime | None
    total_tokens_used: int
