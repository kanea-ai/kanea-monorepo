from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.domain.enums import MemberRole


class AdminUserMembership(BaseModel):
    """One workspace the user is a member of, with their role there.
    Embedded in ``AdminUserDetail`` so the back-office can audit a
    user's presence across tenants in a single call."""

    model_config = ConfigDict(from_attributes=True)

    workspace_id: UUID
    workspace_name: str
    workspace_slug: str
    member_id: UUID
    role: MemberRole
    is_suspended: bool


class AdminUserRow(BaseModel):
    """One row in the back-office user list. Mirrors what the grid
    needs without dragging password / oauth secrets across the wire."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: str
    is_superadmin: bool
    is_banned: bool
    sessions_invalidated_at: datetime | None
    created_at: datetime
    workspace_count: int


class AdminUserDetail(BaseModel):
    """Full back-office profile view — same shape as the list row
    plus the per-workspace membership grid."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: str
    is_superadmin: bool
    is_banned: bool
    sessions_invalidated_at: datetime | None
    created_at: datetime
    memberships: list[AdminUserMembership]


class BanUserRequest(BaseModel):
    """Flip the platform-wide ToS ban. ``True`` blocks every
    authenticated request from the user; ``False`` restores access.
    The service refuses to ban a superadmin or self."""

    model_config = ConfigDict(extra="forbid")

    is_banned: bool


class ForcePasswordResetResponse(BaseModel):
    """Returned by the force-reset endpoint. ``simulated_email`` is
    the message we wrote to the API logs (no real email is sent in
    this stage; the field exists so the back-office can preview what
    the user would have seen)."""

    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    sessions_invalidated_at: datetime
    simulated_email: str
