from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import (
    MemberRole,
    MemberType,
    NotificationType,
    OAuthProvider,
    TeamRole,
)


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


class NotificationResponse(BaseModel):
    """Inbox row. Source pointers may be null when the source row was
    deleted; the denormalised `preview` survives so the bell still
    reads sensibly."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: NotificationType
    source_task_id: UUID | None
    source_comment_id: UUID | None
    source_member_id: UUID | None
    source_member_name: str | None
    preview: str
    read_at: datetime | None
    created_at: datetime


class NotificationCountResponse(BaseModel):
    unread: int


class MeWorkspaceOption(BaseModel):
    """One workspace the current user belongs to. Drives the sidebar
    switcher and the /workspaces tile picker. `is_current` is true for
    the workspace the active JWT is bound to so the UI can render the
    badge / hide the menu item that would self-switch."""

    model_config = ConfigDict(from_attributes=True)

    workspace_id: UUID
    name: str
    role: MemberRole
    member_id: UUID
    is_current: bool


class CreateMyWorkspaceRequest(BaseModel):
    """Authenticated user mints a brand-new workspace under their
    existing User row. Distinct from /auth/register, which creates the
    User. The new workspace's owner is the calling user."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)


class CreateMyWorkspaceResponse(BaseModel):
    """Workspace summary + a fresh access token bound to the new
    membership. The frontend swaps its localStorage token to this so
    the user lands inside the new workspace immediately."""

    model_config = ConfigDict(from_attributes=True)

    workspace_id: UUID
    name: str
    member_id: UUID
    access_token: str
    expires_in: int
