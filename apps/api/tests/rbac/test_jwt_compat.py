"""Tests for the WORKSPACE_MEMBER → WORKSPACE_USER JWT compat shim.

Migration 0021 renamed the role enum value, but JWTs minted before
the deploy still carry the old string. ``_decode_principal`` maps it
transparently so existing sessions don't 401 mid-flight.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
from fastapi.security import HTTPAuthorizationCredentials

from app.api.deps import _decode_principal
from app.core.config import settings
from app.domain.enums import MemberRole, MemberType
from app.infrastructure.security.tokens import JwtSettings, JwtTokenService


def _token_service() -> JwtTokenService:
    return JwtTokenService(
        JwtSettings(
            secret=settings.jwt_secret,
            algorithm=settings.jwt_algorithm,
            human_ttl_seconds=settings.jwt_human_ttl_seconds,
            agent_ttl_seconds=settings.jwt_agent_ttl_seconds,
            issuer=settings.jwt_issuer,
        )
    )


def _legacy_member_token(*, role_str: str = "WORKSPACE_MEMBER") -> str:
    """Forge a JWT carrying a (potentially legacy) role claim. We
    construct it directly rather than going through issue_human_token
    so we can pin the role string the way an old token would."""
    now = datetime.now(UTC)
    payload = {
        "iss": settings.jwt_issuer,
        "sub": str(uuid4()),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=1)).timestamp()),
        "workspace_id": str(uuid4()),
        "type": MemberType.HUMAN.value,
        "priority": 5,
        "role": role_str,
        "scope": "human",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def test_legacy_workspace_member_role_decodes_as_user() -> None:
    token = _legacy_member_token(role_str="WORKSPACE_MEMBER")
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    principal = _decode_principal(creds, _token_service())
    assert principal.role is MemberRole.WORKSPACE_USER


def test_new_workspace_user_role_decodes_unchanged() -> None:
    token = _legacy_member_token(role_str="WORKSPACE_USER")
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    principal = _decode_principal(creds, _token_service())
    assert principal.role is MemberRole.WORKSPACE_USER


def test_admin_role_unaffected_by_shim() -> None:
    token = _legacy_member_token(role_str="WORKSPACE_ADMIN")
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    principal = _decode_principal(creds, _token_service())
    assert principal.role is MemberRole.WORKSPACE_ADMIN
