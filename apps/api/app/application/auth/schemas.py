from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class RegisterRequest(BaseModel):
    """Self-service signup: provisions a Workspace, the inaugural HUMAN
    Member (priority=1, the highest rank — workspace owner), and that
    member's Credentials in one shot. Caller is auto-logged-in via the
    returned token."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    # 8 char minimum is a baseline; OWASP-style strength rules can be
    # layered on later without breaking this contract.
    password: str = Field(min_length=8, max_length=256)
    full_name: str = Field(min_length=1, max_length=120)
    workspace_name: str = Field(min_length=1, max_length=120)


class AgentTokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: UUID
    secret: str = Field(min_length=1, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class OAuthCallbackRequest(BaseModel):
    """Internal value object — the auth route hands these to the service
    after parsing the GET callback's query params."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=2048)
    redirect_uri: str
