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


class WorkspaceOption(BaseModel):
    """One pickable workspace in the multi-workspace login response.
    Returned to the UI alongside a short-lived selection token; the
    caller exchanges (selection_token, workspace_id) at
    /auth/select-workspace for the final access_token."""

    workspace_id: UUID
    name: str
    role: str  # WORKSPACE_OWNER / ADMIN / MEMBER


class LoginResponse(BaseModel):
    """Branched response. Three shapes share this envelope:

    1. Single-workspace user → ``access_token`` is set, both flags
       false.
    2. Multi-workspace user → ``requires_selection=True`` with a
       ``selection_token`` and the ``workspaces`` list.
    3. Brand-new SSO user → ``requires_onboarding=True`` with an
       ``onboarding_token`` and a ``suggested_workspace_name``
       preview; the caller exchanges that token at
       ``/auth/complete-oauth-onboarding`` once the user has picked
       a workspace name.

    Both flags are mutually exclusive; the FE switches on them in
    that order (onboarding wins over selection, both win over the
    happy path)."""

    requires_selection: bool = False
    requires_onboarding: bool = False
    access_token: str | None = None
    token_type: str = "bearer"
    expires_in: int | None = None
    selection_token: str | None = None
    workspaces: list[WorkspaceOption] | None = None
    onboarding_token: str | None = None
    suggested_workspace_name: str | None = None


class CompleteOAuthOnboardingRequest(BaseModel):
    """Second leg of the SSO signup flow. The caller holds an
    onboarding token minted by ``/auth/oauth/{provider}/callback``
    and supplies the workspace name the user chose on the
    ``/onboarding/workspace`` screen."""

    model_config = ConfigDict(extra="forbid")

    onboarding_token: str = Field(min_length=1)
    workspace_name: str = Field(min_length=1, max_length=120)


class SelectWorkspaceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selection_token: str = Field(min_length=1)
    workspace_id: UUID


class SwitchWorkspaceRequest(BaseModel):
    """Authenticated equivalent of select-workspace: an already-signed-
    in user reissues their token bound to a different workspace they
    belong to. Drives the sidebar switcher."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID


class OAuthCallbackRequest(BaseModel):
    """Internal value object — the auth route hands these to the service
    after parsing the GET callback's query params."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=2048)
    redirect_uri: str
