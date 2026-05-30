from __future__ import annotations

import base64
import json
import secrets
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from app.api.deps import AuthServiceDep, RawPrincipalDep, get_oauth_client, get_settings
from app.application.auth.schemas import (
    AgentTokenRequest,
    CompleteOAuthOnboardingRequest,
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    SelectWorkspaceRequest,
    SwitchWorkspaceRequest,
    TokenResponse,
)
from app.core.config import Settings
from app.domain.enums import OAuthProvider
from app.domain.exceptions import (
    AuthenticationError,
    EmailAlreadyExistsError,
    WorkspaceNameConflictError,
)

__all__ = ["router"]

router = APIRouter(prefix="/auth", tags=["auth"])

_OAUTH_STATE_COOKIE = "kanea_oauth_state"
_OAUTH_STATE_TTL_SECONDS = 600


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, service: AuthServiceDep) -> TokenResponse:
    try:
        return await service.register(payload)
    except EmailAlreadyExistsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except WorkspaceNameConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/login", response_model=LoginResponse, status_code=status.HTTP_200_OK)
async def login(payload: LoginRequest, service: AuthServiceDep) -> LoginResponse:
    """Phase 1 multi-tenancy. Returns either an access_token (single
    workspace) or a selection_token + workspaces list (multi-workspace
    user picks one). Both shapes share LoginResponse — switch on
    requires_selection client-side."""
    try:
        return await service.login(payload)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


@router.post(
    "/select-workspace",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
)
async def select_workspace(
    payload: SelectWorkspaceRequest, service: AuthServiceDep
) -> TokenResponse:
    """Exchange a short-lived selection token + a chosen workspace_id
    for the final access token. The user's membership in the workspace
    is verified — the selection token alone is not enough."""
    try:
        return await service.select_workspace(payload)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


@router.post(
    "/switch-workspace",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
)
async def switch_workspace(
    payload: SwitchWorkspaceRequest,
    principal: RawPrincipalDep,
    service: AuthServiceDep,
) -> TokenResponse:
    """Already-signed-in user reissues their access token bound to a
    different workspace they belong to. Distinct from
    /auth/select-workspace, which is the post-login picker that
    requires a selection_token. Drives the sidebar switcher.

    Uses ``RawPrincipalDep`` so a member who is suspended in their
    *current* workspace can still hit this endpoint to escape into
    another workspace where their membership is active. The auth
    service still verifies the requester holds a membership in the
    target workspace.
    Returns 401 when the user has no membership in the requested
    workspace — same shape we use for cross-tenant attempts."""
    try:
        return await service.switch_workspace(principal, payload)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


@router.post("/agent-token", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def agent_token(payload: AgentTokenRequest, service: AuthServiceDep) -> TokenResponse:
    try:
        return await service.issue_agent_token(payload)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


# ---------- OAuth ----------
#
# Two endpoints per provider:
#   GET /oauth/{provider}/login    -> 302 to provider's authorize URL
#   GET /oauth/{provider}/callback -> verifies state, exchanges code,
#                                     issues a JWT, 302 to the frontend
#                                     callback page with `?token=…`.
#
# CSRF: a random `state` is stored in a httpOnly cookie at /login and
# echoed via the provider's redirect; /callback rejects mismatches.


def _redirect_uri(settings: Settings, provider: OAuthProvider) -> str:
    base = settings.api_base_url.rstrip("/")
    return f"{base}/api/v1/auth/oauth/{provider.value.lower()}/callback"


def _normalize_provider(provider: str) -> OAuthProvider:
    """The OAuthProvider enum stores values uppercase (matches the DB
    column), but URLs convention is lowercase — and that's what we
    register with Google/GitHub as the redirect URI, so that's the case
    they bounce back with. Accept either by upper-casing before
    constructing the enum."""
    try:
        return OAuthProvider(provider.upper())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unsupported oauth provider: {provider}",
        ) from exc


@router.get("/oauth/{provider}/login")
async def oauth_login(
    provider: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> RedirectResponse:
    provider_enum = _normalize_provider(provider)
    client = get_oauth_client(provider_enum, settings)
    state = secrets.token_urlsafe(32)
    redirect_uri = _redirect_uri(settings, provider_enum)

    response = RedirectResponse(client.authorize_url(redirect_uri, state))
    response.set_cookie(
        key=_OAUTH_STATE_COOKIE,
        value=state,
        max_age=_OAUTH_STATE_TTL_SECONDS,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return response


@router.get("/oauth/{provider}/callback")
async def oauth_callback(
    provider: str,
    request: Request,
    service: AuthServiceDep,
    settings: Annotated[Settings, Depends(get_settings)],
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    provider_enum = _normalize_provider(provider)
    if error:
        # Provider denied (user cancelled / consent failed). Bounce back
        # to the frontend with the error so it can render a message.
        return _redirect_to_frontend(settings, error=error)

    if not code or not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="missing code or state in oauth callback",
        )

    cookie_state = request.cookies.get(_OAUTH_STATE_COOKIE)
    if not cookie_state or not secrets.compare_digest(cookie_state, state):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="oauth state mismatch — possible CSRF",
        )

    client = get_oauth_client(provider_enum, settings)
    try:
        identity = await client.fetch_identity(code, _redirect_uri(settings, provider_enum))
    except Exception as exc:  # — provider failures map to 502
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"oauth provider error: {exc}",
        ) from exc

    login_resp = await service.oauth_login(identity)

    # Three shapes (priority order on the FE matches this):
    # 1. requires_onboarding — brand-new SSO user, FE prompts for a
    #    workspace name on /onboarding/workspace.
    # 2. requires_selection  — multi-workspace user, FE shows the
    #    picker on /workspaces.
    # 3. happy path          — single-workspace user, FE stores the
    #    token and lands them on /.
    if login_resp.requires_onboarding:
        response = _redirect_to_frontend(
            settings,
            onboarding_token=login_resp.onboarding_token,
            suggested_workspace_name=login_resp.suggested_workspace_name,
        )
    elif login_resp.requires_selection:
        response = _redirect_to_frontend(
            settings,
            selection_token=login_resp.selection_token,
            workspaces=login_resp.workspaces,
        )
    else:
        response = _redirect_to_frontend(settings, token=login_resp.access_token)
    # Clear the state cookie now that it's been consumed.
    response.delete_cookie(_OAUTH_STATE_COOKIE, path="/")
    return response


@router.post(
    "/complete-oauth-onboarding",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
)
async def complete_oauth_onboarding(
    payload: CompleteOAuthOnboardingRequest,
    service: AuthServiceDep,
) -> TokenResponse:
    """Second leg of the SSO signup flow. Caller holds the
    ``onboarding_token`` minted on the OAuth callback and supplies
    the chosen workspace name. We provision the User + Workspace +
    Member trio with that name and return a real access token.

    Errors:
      - 401: onboarding token is expired, malformed, or wrong-scope.
      - 409: ``workspace_name`` is already taken on the platform.
    """
    try:
        return await service.complete_oauth_onboarding(
            onboarding_token=payload.onboarding_token,
            workspace_name=payload.workspace_name.strip(),
        )
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except WorkspaceNameConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


def _redirect_to_frontend(
    settings: Settings,
    *,
    token: str | None = None,
    selection_token: str | None = None,
    workspaces: list | None = None,
    onboarding_token: str | None = None,
    suggested_workspace_name: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    params: dict[str, str] = {}
    if token is not None:
        params["token"] = token
    if selection_token is not None:
        params["selection_token"] = selection_token
    if workspaces is not None:
        # Embed workspaces alongside the selection token so the picker
        # page can render without a follow-up api round-trip. Base64url
        # of compact JSON keeps the URL clean and pop-safe across the
        # tiny realistic counts (<10 workspaces).
        payload = json.dumps([w.model_dump(mode="json") for w in workspaces], separators=(",", ":"))
        params["workspaces"] = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")
    if onboarding_token is not None:
        params["onboarding_token"] = onboarding_token
    if suggested_workspace_name is not None:
        params["suggested_workspace_name"] = suggested_workspace_name
    if error is not None:
        params["error"] = error
    suffix = f"?{urlencode(params)}" if params else ""
    return RedirectResponse(f"{settings.oauth_post_login_redirect}{suffix}")
