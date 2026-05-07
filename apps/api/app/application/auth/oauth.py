"""OAuth provider abstraction.

Each provider knows how to:
  1) build an authorize URL (used to redirect the user to the provider),
  2) exchange the resulting `code` for an access token,
  3) fetch a normalized identity (provider, id, email, name) using that token.

We don't store provider tokens — they're used once to verify identity, then
discarded. Long-term identity is the (provider, oauth_id) pair persisted on
Credentials.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from urllib.parse import urlencode

import httpx

from app.domain.enums import OAuthProvider

logger = logging.getLogger(__name__)


def _check_response(stage: str, resp: httpx.Response) -> None:
    """Like raise_for_status, but bakes the response body into the error
    message and emits a structured warning to the app log. OAuth provider
    errors are otherwise opaque (httpx default just says "404 Not Found"
    or "400 Bad Request") — for diagnosis you need the body, which is
    where Google/GitHub put `redirect_uri_mismatch`, `invalid_client`,
    rate-limit hints, etc. Truncated to 1KB to bound log spam."""
    if not resp.is_error:
        return
    body = resp.text[:1024]
    logger.warning(
        "oauth provider error in %s: status=%s body=%r",
        stage,
        resp.status_code,
        body,
    )
    raise httpx.HTTPStatusError(
        f"{stage} returned {resp.status_code}: {body}",
        request=resp.request,
        response=resp,
    )


@dataclass(slots=True, frozen=True)
class OAuthIdentity:
    provider: OAuthProvider
    oauth_id: str
    email: str
    name: str


@runtime_checkable
class OAuthClient(Protocol):
    provider: OAuthProvider

    def authorize_url(self, redirect_uri: str, state: str) -> str: ...

    async def fetch_identity(self, code: str, redirect_uri: str) -> OAuthIdentity: ...


@dataclass(slots=True)
class GoogleOAuthClient:
    client_id: str
    client_secret: str
    provider: OAuthProvider = OAuthProvider.GOOGLE

    _AUTHORIZE = "https://accounts.google.com/o/oauth2/v2/auth"
    _TOKEN = "https://oauth2.googleapis.com/token"
    # The universal OAuth2 v3 userinfo endpoint. Doesn't require enabling
    # the People API or the OpenID Connect API on the GCP project — those
    # are separate services that can be off by default, which 403'd the
    # older `openidconnect.googleapis.com/v1/userinfo` URL we used to hit.
    # This one ships with the standard `openid email profile` scopes we
    # already request.
    _USERINFO = "https://www.googleapis.com/oauth2/v3/userinfo"

    def authorize_url(self, redirect_uri: str, state: str) -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "access_type": "online",
            "state": state,
            "prompt": "select_account",
        }
        return f"{self._AUTHORIZE}?{urlencode(params)}"

    async def fetch_identity(self, code: str, redirect_uri: str) -> OAuthIdentity:
        async with httpx.AsyncClient(timeout=10.0) as client:
            token_resp = await client.post(
                self._TOKEN,
                data={
                    "code": code,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            _check_response("google token exchange", token_resp)
            access_token = token_resp.json()["access_token"]

            user_resp = await client.get(
                self._USERINFO,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            _check_response("google userinfo", user_resp)
            user = user_resp.json()

        return OAuthIdentity(
            provider=self.provider,
            oauth_id=str(user["sub"]),
            email=str(user["email"]),
            name=str(user.get("name") or user.get("email") or "").strip(),
        )


@dataclass(slots=True)
class GitHubOAuthClient:
    client_id: str
    client_secret: str
    provider: OAuthProvider = OAuthProvider.GITHUB

    _AUTHORIZE = "https://github.com/login/oauth/authorize"
    _TOKEN = "https://github.com/login/oauth/access_token"
    _USER = "https://api.github.com/user"
    _USER_EMAILS = "https://api.github.com/user/emails"

    def authorize_url(self, redirect_uri: str, state: str) -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "scope": "read:user user:email",
            "state": state,
            "allow_signup": "true",
        }
        return f"{self._AUTHORIZE}?{urlencode(params)}"

    async def fetch_identity(self, code: str, redirect_uri: str) -> OAuthIdentity:
        async with httpx.AsyncClient(timeout=10.0) as client:
            token_resp = await client.post(
                self._TOKEN,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
                headers={"Accept": "application/json"},
            )
            _check_response("github token exchange", token_resp)
            access_token = token_resp.json()["access_token"]

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
            }
            user_resp = await client.get(self._USER, headers=headers)
            _check_response("github user", user_resp)
            user = user_resp.json()

            # GitHub user.email may be null when the user keeps it private.
            # Fall back to the primary verified email from /user/emails.
            email = user.get("email")
            if not email:
                emails_resp = await client.get(self._USER_EMAILS, headers=headers)
                _check_response("github user emails", emails_resp)
                primary = next(
                    (e for e in emails_resp.json() if e.get("primary") and e.get("verified")),
                    None,
                )
                if primary is None:
                    raise ValueError("github account has no verified primary email")
                email = primary["email"]

        return OAuthIdentity(
            provider=self.provider,
            oauth_id=str(user["id"]),
            email=str(email),
            name=str(user.get("name") or user.get("login") or "").strip(),
        )
