from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt

from app.application.auth.oauth import OAuthIdentity
from app.domain.entities import Member, User
from app.domain.enums import MemberType, OAuthProvider

# How long a multi-workspace selection token is valid. Short by design
# — it only spans the few seconds between password verification and the
# workspace-pick click. Longer doesn't help anyone and widens the blast
# radius if a bearer leaks.
SELECTION_TTL_SECONDS = 300

# How long an OAuth onboarding token is valid. Generous enough that a
# user can read the prompt and type a workspace name without rushing,
# tight enough that a leaked token doesn't persist. No DB rows are
# created for an onboarding-token holder, so the blast radius of a
# leak is just "attacker can pick the workspace name for this email".
ONBOARDING_TTL_SECONDS = 600


@dataclass(slots=True)
class JwtSettings:
    secret: str
    algorithm: str
    human_ttl_seconds: int
    agent_ttl_seconds: int
    issuer: str = "kanea-api"


class JwtTokenService:
    def __init__(self, settings: JwtSettings) -> None:
        self._settings = settings

    def issue_human_token(self, member: Member) -> tuple[str, int]:
        return self._issue(member, ttl=self._settings.human_ttl_seconds, scope="human")

    def issue_agent_token(self, member: Member) -> tuple[str, int]:
        return self._issue(member, ttl=self._settings.agent_ttl_seconds, scope="agent")

    def decode(self, token: str) -> dict[str, object]:
        return jwt.decode(
            token,
            self._settings.secret,
            algorithms=[self._settings.algorithm],
            issuer=self._settings.issuer,
            options={"require": ["exp", "iat", "sub"]},
        )

    def issue_selection_token(self, user: User) -> tuple[str, int]:
        """Short-lived token used during the multi-workspace login
        picker. Carries scope='select' and only the user_id — has no
        workspace_id and can't be used to call any business endpoint.
        Exchanged at /auth/select-workspace for a real human token."""
        now = datetime.now(UTC)
        payload: dict[str, object] = {
            "iss": self._settings.issuer,
            "sub": str(user.id),
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=SELECTION_TTL_SECONDS)).timestamp()),
            "scope": "select",
        }
        token = jwt.encode(payload, self._settings.secret, algorithm=self._settings.algorithm)
        return token, SELECTION_TTL_SECONDS

    def decode_selection_token(self, token: str) -> UUID:
        """Verify a selection token and return the user_id sub. Raises
        jwt.PyJWTError on bad signature / expired / wrong scope."""
        payload = self.decode(token)
        if payload.get("scope") != "select":
            raise jwt.InvalidTokenError("not a selection token")
        return UUID(str(payload["sub"]))

    def issue_onboarding_token(self, identity: OAuthIdentity) -> tuple[str, int]:
        """Short-lived token used during the SSO onboarding flow.
        Carries scope='onboarding' and the OAuth identity (provider,
        oauth_id, email, name) — but NO database identifiers, because
        no User / Workspace / Member row exists yet. Exchanged at
        ``/auth/complete-oauth-onboarding`` once the caller has chosen
        a workspace name."""
        now = datetime.now(UTC)
        payload: dict[str, object] = {
            "iss": self._settings.issuer,
            "sub": identity.email,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=ONBOARDING_TTL_SECONDS)).timestamp()),
            "scope": "onboarding",
            "provider": identity.provider.value,
            "oauth_id": identity.oauth_id,
            "email": identity.email,
            "name": identity.name or "",
        }
        token = jwt.encode(payload, self._settings.secret, algorithm=self._settings.algorithm)
        return token, ONBOARDING_TTL_SECONDS

    def decode_onboarding_token(self, token: str) -> OAuthIdentity:
        """Verify an onboarding token and recover the OAuth identity.
        Raises ``jwt.PyJWTError`` on bad signature / expired / wrong
        scope — the service catches and surfaces 401."""
        payload = self.decode(token)
        if payload.get("scope") != "onboarding":
            raise jwt.InvalidTokenError("not an onboarding token")
        provider_raw = str(payload.get("provider", ""))
        try:
            provider = OAuthProvider(provider_raw)
        except ValueError as exc:
            raise jwt.InvalidTokenError("malformed onboarding token") from exc
        name_raw = payload.get("name")
        return OAuthIdentity(
            provider=provider,
            oauth_id=str(payload["oauth_id"]),
            email=str(payload["email"]),
            name=(str(name_raw) if name_raw else None),
        )

    def _issue(self, member: Member, *, ttl: int, scope: str) -> tuple[str, int]:
        if scope == "human" and member.type is not MemberType.HUMAN:
            raise ValueError("human token requested for non-human member")
        if scope == "agent" and member.type is not MemberType.AGENT:
            raise ValueError("agent token requested for non-agent member")

        now = datetime.now(UTC)
        payload: dict[str, object] = {
            "iss": self._settings.issuer,
            "sub": str(member.id),
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=ttl)).timestamp()),
            "workspace_id": str(member.workspace_id),
            "type": member.type.value,
            "priority": member.priority,
            "role": member.role.value,
            "scope": scope,
        }
        token = jwt.encode(payload, self._settings.secret, algorithm=self._settings.algorithm)
        return token, ttl
