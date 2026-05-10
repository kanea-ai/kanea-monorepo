from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.domain.entities import Invite, Member
from app.domain.enums import MemberRole, MemberType, TeamRole


class InviteCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    role: MemberRole = MemberRole.WORKSPACE_USER

    # OWNER must be created via signup, never via invite — workspace
    # ownership transfers are a separate flow with stronger guarantees.
    def is_role_inviteable(self) -> bool:
        return self.role in (MemberRole.WORKSPACE_ADMIN, MemberRole.WORKSPACE_USER)


class InviteCreateResponse(BaseModel):
    """Returned to the inviter exactly once with the raw token. Subsequent
    GETs hash the token before lookup, so we can't show the token again."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    email: str
    role: MemberRole
    expires_at: datetime
    # The shareable URL the inviter copies into chat / email.
    accept_url: str
    # Raw token — exposed once, never persisted in plaintext.
    token: str


class InvitePreviewResponse(BaseModel):
    """What the invitee sees when they open the accept URL — minimal info
    so a leaked token reveals only what's strictly necessary."""

    model_config = ConfigDict(from_attributes=True)

    workspace_name: str
    email: str
    role: MemberRole
    expires_at: datetime


class InviteAcceptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=256)


class MemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    name: str
    email: str | None
    type: MemberType
    role: MemberRole
    priority: int
    team_id: UUID | None
    team_role: TeamRole | None
    is_suspended: bool

    @classmethod
    def from_entity(cls, member: Member) -> MemberResponse:
        return cls(
            id=member.id,
            workspace_id=member.workspace_id,
            name=member.name,
            email=member.email,
            type=member.type,
            role=member.role,
            priority=member.priority,
            team_id=member.team_id,
            team_role=member.team_role,
            is_suspended=member.is_suspended,
        )


class MemberProfileResponse(BaseModel):
    """Priority-scoped profile shape returned by
    ``GET /tenants/members/{id}/profile``. Two flavours:

    * **Full view** — same shape as ``MemberResponse``: every field is
      populated. Returned when the principal is OWNER, the target,
      or an admin whose priority is ≤ the target's priority.
    * **Limited view** — only ``id``, ``name``, ``email``, ``type``
      are populated. Used when a lower-rank admin clicks an actor
      with a higher rank (lower priority number) in the audit log,
      so they get just enough to know who they're looking at without
      exposing role / team / suspension state etc.

    The ``is_limited_view`` flag is the contract the UI keys off of
    when deciding what fields to render."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    name: str
    email: str | None
    type: MemberType
    is_limited_view: bool
    # Restricted fields — nullable in the limited shape.
    role: MemberRole | None = None
    priority: int | None = None
    team_id: UUID | None = None
    team_role: TeamRole | None = None
    is_suspended: bool | None = None

    @classmethod
    def full(cls, member: Member) -> MemberProfileResponse:
        return cls(
            id=member.id,
            workspace_id=member.workspace_id,
            name=member.name,
            email=member.email,
            type=member.type,
            is_limited_view=False,
            role=member.role,
            priority=member.priority,
            team_id=member.team_id,
            team_role=member.team_role,
            is_suspended=member.is_suspended,
        )

    @classmethod
    def limited(cls, member: Member) -> MemberProfileResponse:
        return cls(
            id=member.id,
            workspace_id=member.workspace_id,
            name=member.name,
            email=member.email,
            type=member.type,
            is_limited_view=True,
        )


class MemberStatsResponse(BaseModel):
    """Stats for any member (human or agent). Mirrors the agent
    detail's AgentStats shape — same SQL feeds both — so the
    directory detail dialog can render the same numbers regardless
    of type."""

    model_config = ConfigDict(from_attributes=True)

    assigned_count: int
    completed_count: int
    avg_resolution_seconds: float | None
    accuracy_percent: float | None
    last_activity_at: datetime | None
    total_tokens_used: int


class MemberFilters(BaseModel):
    """Query-string filters for the members directory. All optional;
    the service composes the SQL `WHERE` clause from whichever the
    caller provides. Visibility (which members the caller is allowed
    to see at all) is layered on top by the service — these are the
    "narrowing" filters the user types into the directory page."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    member_id: UUID | None = None
    role: MemberRole | None = None
    team_id: UUID | None = None
    # Members who have at least one task assigned in this project.
    project_id: UUID | None = None
    # Excludes agents from the listing when True. Default keeps the
    # legacy behaviour (everyone, including agents).
    humans_only: bool = False


class UpdateMemberProfileRequest(BaseModel):
    """Admin-only edit of another member's profile. All fields
    optional so a single PATCH can rename, re-role, re-prioritise,
    or any combination. The last-OWNER demotion guard lives in the
    service. Priority is the workspace-wide rank (1 = owner, agents
    typically 2..100); the directory's sort key uses it directly."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    role: MemberRole | None = None
    priority: int | None = Field(default=None, ge=1, le=100)


class AdminSetMemberPasswordRequest(BaseModel):
    """Admin-side password reset payload. Contrast with /me/password
    which requires the principal's current password — admins don't
    have it. The service refuses to write when the underlying User
    has memberships in other workspaces (their credential is shared
    and isn't this admin's to reset)."""

    model_config = ConfigDict(extra="forbid")

    new_password: str = Field(min_length=8, max_length=256)


class SetMemberSuspensionRequest(BaseModel):
    """Admin-only flip of the workspace-scoped soft lock. ``true``
    suspends; ``false`` revokes. The service refuses to suspend the
    last remaining workspace owner so a workspace can't be left with
    no admin path back."""

    model_config = ConfigDict(extra="forbid")

    is_suspended: bool


class SetMemberTeamRequest(BaseModel):
    """Admin-only: assign / unassign a member to a team and set their
    intra-team role. team_id=null clears the assignment (and the
    role); when team_id is set, team_role must also be set."""

    model_config = ConfigDict(extra="forbid")

    team_id: UUID | None = None
    team_role: TeamRole | None = None


def invite_create_response_from_entity(
    invite: Invite, *, raw_token: str, accept_url: str
) -> InviteCreateResponse:
    return InviteCreateResponse(
        id=invite.id,
        workspace_id=invite.workspace_id,
        email=invite.email,
        role=invite.role,
        expires_at=invite.expires_at,
        accept_url=accept_url,
        token=raw_token,
    )
