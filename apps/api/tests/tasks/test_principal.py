"""Tests for the ``get_current_principal`` dependency.

Verifies that the requester's priority is propagated end-to-end from a
JWT into a ``Principal`` — this is what the hierarchy check operates on.
"""

from __future__ import annotations

import jwt
import pytest
from fastapi.security import HTTPAuthorizationCredentials

# The DB-touching ``get_current_principal`` wraps ``_decode_principal``
# with a workspace-suspension lookup. Direct unit tests of the JWT
# decoding path import the raw decoder so they don't need to seed a
# member row.
from app.api.deps import _decode_principal as get_current_principal
from app.application.tasks.schemas import Principal
from app.domain.enums import MemberType
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
def token_service(jwt_settings: JwtSettings) -> JwtTokenService:
    return JwtTokenService(jwt_settings)


def _bearer(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def test_principal_carries_priority_from_human_token(token_service: JwtTokenService) -> None:
    human = make_human(priority=1)  # CEO-rank
    token, _ = token_service.issue_human_token(human)

    principal = get_current_principal(_bearer(token), token_service)

    assert isinstance(principal, Principal)
    assert principal.member_id == human.id
    assert principal.workspace_id == human.workspace_id
    assert principal.type is MemberType.HUMAN
    assert principal.priority == 1
    assert principal.scope == "human"


def test_principal_carries_priority_from_agent_token(token_service: JwtTokenService) -> None:
    agent = make_agent(priority=5)  # Agent-rank
    token, _ = token_service.issue_agent_token(agent)

    principal = get_current_principal(_bearer(token), token_service)

    assert principal.type is MemberType.AGENT
    assert principal.priority == 5
    assert principal.scope == "agent"


def test_invalid_signature_raises_401(
    token_service: JwtTokenService, jwt_settings: JwtSettings
) -> None:
    from fastapi import HTTPException

    other = JwtTokenService(
        JwtSettings(
            secret="different-secret",  # pragma: allowlist secret
            algorithm=jwt_settings.algorithm,
            human_ttl_seconds=jwt_settings.human_ttl_seconds,
            agent_ttl_seconds=jwt_settings.agent_ttl_seconds,
            issuer=jwt_settings.issuer,
        )
    )
    token, _ = other.issue_human_token(make_human())

    with pytest.raises(HTTPException) as excinfo:
        get_current_principal(_bearer(token), token_service)
    assert excinfo.value.status_code == 401


def test_malformed_payload_raises_401(jwt_settings: JwtSettings) -> None:
    from datetime import UTC, datetime, timedelta

    from fastapi import HTTPException

    now = datetime.now(UTC)
    payload = {
        "iss": jwt_settings.issuer,
        "sub": "not-a-uuid",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        "workspace_id": "not-a-uuid",
        "type": "HUMAN",
        "priority": 1,
        "scope": "human",
    }
    token = jwt.encode(payload, jwt_settings.secret, algorithm=jwt_settings.algorithm)
    service = JwtTokenService(jwt_settings)

    with pytest.raises(HTTPException) as excinfo:
        get_current_principal(_bearer(token), service)
    assert excinfo.value.status_code == 401
