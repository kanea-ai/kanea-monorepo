from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

from app.domain.entities import Member
from app.domain.enums import MemberType


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
            "scope": scope,
        }
        token = jwt.encode(payload, self._settings.secret, algorithm=self._settings.algorithm)
        return token, ttl
