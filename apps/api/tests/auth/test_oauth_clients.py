"""Unit-level coverage for the OAuth clients. URL-building paths are
straightforward; HTTP calls are exercised via stubbed httpx.AsyncClient
context managers so we don't hit real Google / GitHub endpoints."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import parse_qs, urlsplit

import pytest

from app.api.deps import get_oauth_client
from app.application.auth.oauth import (
    GitHubOAuthClient,
    GoogleOAuthClient,
)
from app.core.config import Settings
from app.domain.enums import OAuthProvider


def _stub_async_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    post_responses: list[dict],
    get_responses: list[dict],
) -> None:
    """Replace httpx.AsyncClient with a context manager that yields a stub
    whose .post()/.get() return queued responses in order."""

    posts = iter(post_responses)
    gets = iter(get_responses)

    def _make_response(payload: dict) -> MagicMock:
        resp = MagicMock()
        resp.json.return_value = payload
        # `_check_response` (the new wrapper) reads is_error before doing
        # anything else; default-MagicMocks return a truthy mock there,
        # which trips the error path on a happy-path test.
        resp.is_error = False
        resp.status_code = 200
        resp.raise_for_status.return_value = None
        return resp

    stub = MagicMock()
    stub.post = AsyncMock(side_effect=lambda *_a, **_kw: _make_response(next(posts)))
    stub.get = AsyncMock(side_effect=lambda *_a, **_kw: _make_response(next(gets)))

    @asynccontextmanager
    async def _client(*_a, **_kw):
        yield stub

    monkeypatch.setattr("app.application.auth.oauth.httpx.AsyncClient", _client)


def test_google_authorize_url_carries_required_params() -> None:
    client = GoogleOAuthClient(client_id="cid", client_secret="csec")  # pragma: allowlist secret
    url = client.authorize_url("https://app/cb", "the-state")
    qs = parse_qs(urlsplit(url).query)
    assert urlsplit(url).netloc == "accounts.google.com"
    assert qs["client_id"] == ["cid"]
    assert qs["redirect_uri"] == ["https://app/cb"]
    assert qs["state"] == ["the-state"]
    assert qs["response_type"] == ["code"]
    assert "openid" in qs["scope"][0]
    assert "email" in qs["scope"][0]


def test_github_authorize_url_carries_required_params() -> None:
    client = GitHubOAuthClient(client_id="cid", client_secret="csec")  # pragma: allowlist secret
    url = client.authorize_url("https://app/cb", "the-state")
    qs = parse_qs(urlsplit(url).query)
    assert urlsplit(url).netloc == "github.com"
    assert qs["client_id"] == ["cid"]
    assert qs["redirect_uri"] == ["https://app/cb"]
    assert qs["state"] == ["the-state"]
    assert "user:email" in qs["scope"][0]


def test_get_oauth_client_returns_google_when_configured() -> None:
    settings = Settings(
        google_oauth_client_id="g",
        google_oauth_client_secret="s",  # pragma: allowlist secret
    )
    client = get_oauth_client(OAuthProvider.GOOGLE, settings)
    assert isinstance(client, GoogleOAuthClient)


def test_get_oauth_client_returns_github_when_configured() -> None:
    settings = Settings(
        github_oauth_client_id="g",
        github_oauth_client_secret="s",  # pragma: allowlist secret
    )
    client = get_oauth_client(OAuthProvider.GITHUB, settings)
    assert isinstance(client, GitHubOAuthClient)


def test_get_oauth_client_503_when_unconfigured() -> None:
    from fastapi import HTTPException

    settings = Settings()  # all OAuth client ids/secrets empty
    with pytest.raises(HTTPException) as exc_info:
        get_oauth_client(OAuthProvider.GOOGLE, settings)
    assert exc_info.value.status_code == 503


# ---------- fetch_identity (with stubbed httpx) ----------


async def test_google_fetch_identity_returns_normalized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_async_client(
        monkeypatch,
        post_responses=[{"access_token": "g-tok"}],
        get_responses=[{"sub": "google-12345", "email": "alice@kanea.ai", "name": "Alice"}],
    )
    client = GoogleOAuthClient(client_id="cid", client_secret="csec")  # pragma: allowlist secret
    identity = await client.fetch_identity("the-code", "https://app/cb")

    assert identity.provider is OAuthProvider.GOOGLE
    assert identity.oauth_id == "google-12345"
    assert identity.email == "alice@kanea.ai"
    assert identity.name == "Alice"


async def test_github_fetch_identity_uses_inline_email_when_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_async_client(
        monkeypatch,
        post_responses=[{"access_token": "gh-tok"}],
        get_responses=[
            {
                "id": 67890,
                "login": "alice",
                "name": "Alice Github",
                "email": "alice@kanea.ai",
            }
        ],
    )
    client = GitHubOAuthClient(client_id="cid", client_secret="csec")  # pragma: allowlist secret
    identity = await client.fetch_identity("the-code", "https://app/cb")

    assert identity.provider is OAuthProvider.GITHUB
    assert identity.oauth_id == "67890"
    assert identity.email == "alice@kanea.ai"
    assert identity.name == "Alice Github"


async def test_github_fetch_identity_falls_back_to_primary_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the user keeps email private, /user.email is null and we
    fall back to the verified primary entry from /user/emails."""
    _stub_async_client(
        monkeypatch,
        post_responses=[{"access_token": "gh-tok"}],
        get_responses=[
            {"id": 1, "login": "alice", "name": None, "email": None},
            [
                {"email": "noreply@github.com", "primary": False, "verified": True},
                {"email": "alice@kanea.ai", "primary": True, "verified": True},
            ],
        ],
    )
    client = GitHubOAuthClient(client_id="cid", client_secret="csec")  # pragma: allowlist secret
    identity = await client.fetch_identity("the-code", "https://app/cb")

    assert identity.email == "alice@kanea.ai"
    # Falls back to login when name is missing.
    assert identity.name == "alice"


async def test_google_fetch_identity_surfaces_provider_error_body(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """When the token-exchange call fails (e.g. invalid_client / redirect
    URI mismatch), the raised exception must carry the provider's body so
    Cloud Run logs show *why*, and the message also makes it into the
    structured app log."""
    from contextlib import asynccontextmanager
    from unittest.mock import AsyncMock, MagicMock

    import httpx

    error_resp = MagicMock()
    error_resp.is_error = True
    error_resp.status_code = 401
    error_resp.text = '{"error":"invalid_client","error_description":"bad secret"}'
    error_resp.request = httpx.Request("POST", "https://oauth2.googleapis.com/token")

    stub = MagicMock()
    stub.post = AsyncMock(return_value=error_resp)

    @asynccontextmanager
    async def _client(*_a, **_kw):
        yield stub

    monkeypatch.setattr("app.application.auth.oauth.httpx.AsyncClient", _client)

    client = GoogleOAuthClient(client_id="cid", client_secret="csec")  # pragma: allowlist secret

    with (
        caplog.at_level("WARNING", logger="app.application.auth.oauth"),
        pytest.raises(httpx.HTTPStatusError, match="invalid_client"),
    ):
        await client.fetch_identity("c", "https://app/cb")

    # The structured log captures status + body for ops to grep on.
    assert any("invalid_client" in rec.message for rec in caplog.records)
    assert any("status=401" in rec.message for rec in caplog.records)


async def test_github_fetch_identity_raises_when_no_verified_primary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_async_client(
        monkeypatch,
        post_responses=[{"access_token": "gh-tok"}],
        get_responses=[
            {"id": 1, "login": "alice", "name": None, "email": None},
            [{"email": "x@y.z", "primary": True, "verified": False}],
        ],
    )
    client = GitHubOAuthClient(client_id="cid", client_secret="csec")  # pragma: allowlist secret
    with pytest.raises(ValueError, match="verified primary email"):
        await client.fetch_identity("c", "r")
