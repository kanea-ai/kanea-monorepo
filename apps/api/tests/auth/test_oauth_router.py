from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_auth_service, get_settings
from app.application.auth.oauth import OAuthIdentity
from app.application.auth.schemas import LoginResponse
from app.core.config import Settings
from app.domain.enums import OAuthProvider
from app.main import app


@pytest.fixture
def auth_service() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def settings() -> Settings:
    # Both providers configured so the route doesn't 503. Cookie secure
    # off so the TestClient can read the Set-Cookie header without TLS.
    return Settings(
        google_oauth_client_id="google-client-id",
        google_oauth_client_secret="google-client-secret",  # pragma: allowlist secret
        github_oauth_client_id="github-client-id",
        github_oauth_client_secret="github-client-secret",  # pragma: allowlist secret
        cookie_secure=False,
        api_base_url="http://localhost:8000",
        oauth_post_login_redirect="http://localhost:3000/auth/callback",
    )


@pytest.fixture
def client(auth_service: AsyncMock, settings: Settings) -> Iterator[TestClient]:
    app.dependency_overrides[get_auth_service] = lambda: auth_service
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


# ---------- /oauth/{provider}/login ----------


def test_oauth_login_redirects_to_google_with_state_cookie(
    client: TestClient, settings: Settings
) -> None:
    response = client.get("/api/v1/auth/oauth/GOOGLE/login", follow_redirects=False)
    assert response.status_code == 307
    location = response.headers["location"]
    assert location.startswith("https://accounts.google.com/o/oauth2/v2/auth?")

    # Redirect URL should carry our client_id, the redirect_uri pointing at
    # this api's callback path, and a state we'll later verify against the
    # cookie.
    qs = parse_qs(urlsplit(location).query)
    assert qs["client_id"] == [settings.google_oauth_client_id]
    assert qs["redirect_uri"] == ["http://localhost:8000/api/v1/auth/oauth/google/callback"]
    state = qs["state"][0]
    assert state  # non-empty random token

    # State cookie set with the same value, httpOnly, lax SameSite.
    cookie = next(c for c in response.cookies.jar if c.name == "kanea_oauth_state")
    assert cookie.value == state


def test_oauth_login_503_when_provider_unconfigured(client: TestClient) -> None:
    # Override settings to clear github creds.
    app.dependency_overrides[get_settings] = lambda: Settings(
        google_oauth_client_id="x",
        google_oauth_client_secret="y",  # pragma: allowlist secret
        github_oauth_client_id="",
        github_oauth_client_secret="",
    )
    response = client.get("/api/v1/auth/oauth/GITHUB/login", follow_redirects=False)
    assert response.status_code == 503
    assert "github" in response.json()["detail"]


def test_oauth_login_accepts_lowercase_provider(client: TestClient) -> None:
    """Real-world callbacks come from Google/GitHub with the case we
    registered as the redirect URI — lowercase. Both cases must work."""
    response = client.get("/api/v1/auth/oauth/google/login", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"].startswith("https://accounts.google.com/o/oauth2/v2/auth?")


def test_oauth_login_unknown_provider_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/auth/oauth/twitter/login", follow_redirects=False)
    assert response.status_code == 404
    assert "twitter" in response.json()["detail"]


# ---------- /oauth/{provider}/callback ----------


def test_oauth_callback_happy_path_redirects_to_frontend_with_token(
    client: TestClient, auth_service: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Set the state cookie, mock the OAuth client's fetch_identity, hit
    the callback, expect a redirect to the frontend with ?token=…"""

    # Mock the OAuthClient that get_oauth_client would build, so we don't
    # actually call Google's APIs.
    mock_client = MagicMock()
    mock_client.fetch_identity = AsyncMock(
        return_value=OAuthIdentity(
            provider=OAuthProvider.GOOGLE,
            oauth_id="g-12345",
            email="alice@kanea.ai",
            name="Alice",
        )
    )
    monkeypatch.setattr("app.api.v1.auth.get_oauth_client", lambda *_a, **_kw: mock_client)

    auth_service.oauth_login.return_value = LoginResponse(
        requires_selection=False, access_token="signed.jwt", expires_in=3600
    )

    client.cookies.set("kanea_oauth_state", "the-state-token")
    response = client.get(
        "/api/v1/auth/oauth/GOOGLE/callback?code=auth-code&state=the-state-token",
        follow_redirects=False,
    )

    assert response.status_code == 307
    assert response.headers["location"] == ("http://localhost:3000/auth/callback?token=signed.jwt")
    auth_service.oauth_login.assert_awaited_once()


def test_oauth_callback_multi_workspace_redirects_with_selection_token(
    client: TestClient, auth_service: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Multi-workspace OAuth users get bounced to the frontend with
    the selection token AND a base64url-encoded workspaces blob, so
    the picker can render without a follow-up api round-trip."""
    import base64
    import json
    from uuid import uuid4

    from app.application.auth.schemas import WorkspaceOption
    from app.domain.enums import MemberRole

    mock_client = MagicMock()
    mock_client.fetch_identity = AsyncMock(
        return_value=OAuthIdentity(
            provider=OAuthProvider.GOOGLE,
            oauth_id="g-12345",
            email="alice@kanea.ai",
            name="Alice",
        )
    )
    monkeypatch.setattr("app.api.v1.auth.get_oauth_client", lambda *_a, **_kw: mock_client)

    ws_a, ws_b = uuid4(), uuid4()
    auth_service.oauth_login.return_value = LoginResponse(
        requires_selection=True,
        selection_token="sel.jwt",
        workspaces=[
            WorkspaceOption(workspace_id=ws_a, name="Acme", role=MemberRole.WORKSPACE_OWNER),
            WorkspaceOption(workspace_id=ws_b, name="Beta", role=MemberRole.WORKSPACE_MEMBER),
        ],
    )

    client.cookies.set("kanea_oauth_state", "the-state-token")
    response = client.get(
        "/api/v1/auth/oauth/GOOGLE/callback?code=auth-code&state=the-state-token",
        follow_redirects=False,
    )

    assert response.status_code == 307
    location = response.headers["location"]
    assert location.startswith("http://localhost:3000/auth/callback?")
    qs = parse_qs(urlsplit(location).query)
    assert qs["selection_token"] == ["sel.jwt"]
    assert "token" not in qs

    # Decode the embedded workspaces blob and verify both made it
    # through with stable role names.
    decoded = json.loads(base64.urlsafe_b64decode(qs["workspaces"][0] + "==").decode("utf-8"))
    assert {w["workspace_id"] for w in decoded} == {str(ws_a), str(ws_b)}
    assert {w["role"] for w in decoded} == {"WORKSPACE_OWNER", "WORKSPACE_MEMBER"}


def test_oauth_callback_rejects_state_mismatch(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    mock_client = MagicMock()
    monkeypatch.setattr("app.api.v1.auth.get_oauth_client", lambda *_a, **_kw: mock_client)
    client.cookies.set("kanea_oauth_state", "real-state")
    response = client.get(
        "/api/v1/auth/oauth/GOOGLE/callback?code=c&state=tampered",
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "state mismatch" in response.json()["detail"]


def test_oauth_callback_propagates_provider_error(client: TestClient) -> None:
    response = client.get(
        "/api/v1/auth/oauth/GOOGLE/callback?error=access_denied",
        follow_redirects=False,
    )
    assert response.status_code == 307
    assert "error=access_denied" in response.headers["location"]


def test_oauth_callback_missing_code_or_state_is_400(client: TestClient) -> None:
    response = client.get(
        "/api/v1/auth/oauth/GOOGLE/callback?code=just-a-code",
        follow_redirects=False,
    )
    assert response.status_code == 400


def test_oauth_callback_provider_failure_maps_to_502(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    mock_client = MagicMock()
    mock_client.fetch_identity = AsyncMock(side_effect=ValueError("boom"))
    monkeypatch.setattr("app.api.v1.auth.get_oauth_client", lambda *_a, **_kw: mock_client)
    client.cookies.set("kanea_oauth_state", "s")
    response = client.get(
        "/api/v1/auth/oauth/GOOGLE/callback?code=c&state=s",
        follow_redirects=False,
    )
    assert response.status_code == 502
    assert "boom" in response.json()["detail"]
