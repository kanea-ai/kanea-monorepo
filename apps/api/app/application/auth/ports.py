from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from app.domain.entities import Credentials, Member


@runtime_checkable
class MemberRepository(Protocol):
    async def get_by_email(self, email: str) -> Member | None: ...
    async def get_by_id(self, member_id: UUID) -> Member | None: ...


@runtime_checkable
class CredentialsRepository(Protocol):
    async def get_for_member(self, member_id: UUID) -> Credentials | None: ...


@runtime_checkable
class PasswordHasher(Protocol):
    def verify(self, plain: str, hashed: str) -> bool: ...
    def hash(self, plain: str) -> str: ...


@runtime_checkable
class TokenService(Protocol):
    def issue_human_token(self, member: Member) -> tuple[str, int]:
        """Returns (token, expires_in_seconds)."""

    def issue_agent_token(self, member: Member) -> tuple[str, int]:
        """Returns (token, expires_in_seconds)."""
