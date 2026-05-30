from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.infrastructure.security.tokens import JwtSettings, JwtTokenService
from tests.auth.factories import make_agent, make_human


@pytest.fixture
def jwt_settings() -> JwtSettings:
    return JwtSettings(
        secret="unit-test-secret",  # pragma: allowlist secret
        algorithm="HS256",
        human_ttl_seconds=3600,
        agent_ttl_seconds=900,
        issuer="kanea-test",
    )


@pytest.fixture
def service(jwt_settings: JwtSettings) -> JwtTokenService:
    return JwtTokenService(jwt_settings)


def test_issue_human_token_roundtrip(service: JwtTokenService, jwt_settings: JwtSettings) -> None:
    human = make_human()

    token, ttl = service.issue_human_token(human)

    assert ttl == 3600
    payload = service.decode(token)
    assert payload["sub"] == str(human.id)
    assert payload["workspace_id"] == str(human.workspace_id)
    assert payload["scope"] == "human"
    assert payload["type"] == "HUMAN"
    assert payload["iss"] == jwt_settings.issuer
    assert isinstance(payload["exp"], int)
    assert isinstance(payload["iat"], int)
    assert payload["exp"] - payload["iat"] == ttl


def test_issue_agent_token_roundtrip(service: JwtTokenService) -> None:
    agent = make_agent()

    token, ttl = service.issue_agent_token(agent)

    assert ttl == 900
    payload = service.decode(token)
    assert payload["sub"] == str(agent.id)
    assert payload["scope"] == "agent"
    assert payload["type"] == "AGENT"


def test_human_token_rejects_agent(service: JwtTokenService) -> None:
    with pytest.raises(ValueError):
        service.issue_human_token(make_agent())


def test_agent_token_rejects_human(service: JwtTokenService) -> None:
    with pytest.raises(ValueError):
        service.issue_agent_token(make_human())


def test_decode_rejects_wrong_secret(service: JwtTokenService, jwt_settings: JwtSettings) -> None:
    token, _ = service.issue_human_token(make_human())
    other = JwtTokenService(
        JwtSettings(
            secret="different-secret",  # pragma: allowlist secret
            algorithm=jwt_settings.algorithm,
            human_ttl_seconds=jwt_settings.human_ttl_seconds,
            agent_ttl_seconds=jwt_settings.agent_ttl_seconds,
            issuer=jwt_settings.issuer,
        )
    )
    with pytest.raises(jwt.InvalidSignatureError):
        other.decode(token)


def test_decode_rejects_expired(jwt_settings: JwtSettings) -> None:
    expired = JwtTokenService(
        JwtSettings(
            secret=jwt_settings.secret,
            algorithm=jwt_settings.algorithm,
            human_ttl_seconds=-10,
            agent_ttl_seconds=jwt_settings.agent_ttl_seconds,
            issuer=jwt_settings.issuer,
        )
    )
    token, _ = expired.issue_human_token(make_human())
    with pytest.raises(jwt.ExpiredSignatureError):
        expired.decode(token)


def test_decode_rejects_missing_required_claims(
    service: JwtTokenService, jwt_settings: JwtSettings
) -> None:
    payload = {
        "iss": jwt_settings.issuer,
        "iat": int(datetime.now(UTC).timestamp()),
        "exp": int((datetime.now(UTC) + timedelta(minutes=5)).timestamp()),
        # missing 'sub'
    }
    bad = jwt.encode(payload, jwt_settings.secret, algorithm=jwt_settings.algorithm)
    with pytest.raises(jwt.MissingRequiredClaimError):
        service.decode(bad)


def test_onboarding_token_roundtrip(service: JwtTokenService) -> None:
    """An onboarding token preserves the OAuth identity exactly,
    including a None name (which encodes as the empty string and
    decodes back to None)."""
    from app.application.auth.oauth import OAuthIdentity
    from app.domain.enums import OAuthProvider

    identity = OAuthIdentity(
        provider=OAuthProvider.GOOGLE,
        oauth_id="google-sub-12345",
        email="alice@kanea.ai",
        name="Alice",
    )
    token, ttl = service.issue_onboarding_token(identity)
    assert ttl == 600

    recovered = service.decode_onboarding_token(token)
    assert recovered.provider is OAuthProvider.GOOGLE
    assert recovered.oauth_id == "google-sub-12345"
    assert recovered.email == "alice@kanea.ai"
    assert recovered.name == "Alice"


def test_onboarding_token_roundtrip_no_name(service: JwtTokenService) -> None:
    from app.application.auth.oauth import OAuthIdentity
    from app.domain.enums import OAuthProvider

    identity = OAuthIdentity(
        provider=OAuthProvider.GITHUB,
        oauth_id="gh-99",
        email="anon@example.com",
        name=None,
    )
    token, _ttl = service.issue_onboarding_token(identity)
    recovered = service.decode_onboarding_token(token)
    assert recovered.name is None


def test_onboarding_token_rejects_wrong_scope(service: JwtTokenService) -> None:
    """A token with the wrong scope (e.g. a human access token) must
    not pass decode_onboarding_token."""
    import jwt as pyjwt
    import pytest

    from tests.auth.factories import make_human

    human_token, _ttl = service.issue_human_token(make_human())
    with pytest.raises(pyjwt.InvalidTokenError):
        service.decode_onboarding_token(human_token)


def test_onboarding_token_rejects_unknown_provider(
    service: JwtTokenService, jwt_settings: JwtSettings
) -> None:
    """A tampered token claiming an unknown provider is rejected
    rather than silently producing a malformed identity."""
    from datetime import UTC, datetime, timedelta

    import jwt as pyjwt
    import pytest

    now = datetime.now(UTC)
    payload = {
        "iss": jwt_settings.issuer,
        "sub": "x@y.com",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        "scope": "onboarding",
        "provider": "FACEBOOK",  # not in OAuthProvider
        "oauth_id": "fb-1",
        "email": "x@y.com",
        "name": "",
    }
    bad = pyjwt.encode(payload, jwt_settings.secret, algorithm=jwt_settings.algorithm)
    with pytest.raises(pyjwt.InvalidTokenError):
        service.decode_onboarding_token(bad)
