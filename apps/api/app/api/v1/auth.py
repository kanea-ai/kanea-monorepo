from __future__ import annotations

import secrets
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from app.api.deps import AuthServiceDep, get_oauth_client, get_settings
from app.application.auth.schemas import (
    AgentTokenRequest,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
)
from app.core.config import Settings
from app.domain.enums import OAuthProvider
from app.domain.exceptions import AuthenticationError, EmailAlreadyExistsError

router = APIRouter(prefix="/auth", tags=["auth"])

_OAUTH_STATE_COOKIE = "kanea_oauth_state"
_OAUTH_STATE_TTL_SECONDS = 600


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, service: AuthServiceDep) -> TokenResponse:
    try:
        return await service.register(payload)
    except EmailAlreadyExistsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/login", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def login(payload: LoginRequest, service: AuthServiceDep) -> TokenResponse:
    try:
        return await service.login(payload)
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

    token_resp = await service.oauth_login(identity)

    response = _redirect_to_frontend(settings, token=token_resp.access_token)
    # Clear the state cookie now that it's been consumed.
    response.delete_cookie(_OAUTH_STATE_COOKIE, path="/")
    return response


def _redirect_to_frontend(
    settings: Settings, *, token: str | None = None, error: str | None = None
) -> RedirectResponse:
    params: dict[str, str] = {}
    if token is not None:
        params["token"] = token
    if error is not None:
        params["error"] = error
    suffix = f"?{urlencode(params)}" if params else ""
    return RedirectResponse(f"{settings.oauth_post_login_redirect}{suffix}")
