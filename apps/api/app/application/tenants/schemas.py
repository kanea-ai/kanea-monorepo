from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.domain.entities import Invite, Member
from app.domain.enums import MemberRole, MemberType


class InviteCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    role: MemberRole = MemberRole.MEMBER

    # OWNER must be created via signup, never via invite — workspace
    # ownership transfers are a separate flow with stronger guarantees.
    def is_role_inviteable(self) -> bool:
        return self.role in (MemberRole.ADMIN, MemberRole.MEMBER)


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
        )


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
