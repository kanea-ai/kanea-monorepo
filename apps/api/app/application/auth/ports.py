from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from app.domain.entities import Credentials, Member, User, Workspace
from app.domain.enums import OAuthProvider


@runtime_checkable
class MemberRepository(Protocol):
    async def get_by_email(self, email: str) -> Member | None: ...
    async def get_by_id(self, member_id: UUID) -> Member | None: ...
    async def create(self, member: Member) -> Member: ...
    async def heartbeat(self, member_id: UUID) -> None: ...
    async def list_for_user(self, user_id: UUID) -> list[Member]: ...


@runtime_checkable
class UserRepository(Protocol):
    async def get_by_id(self, user_id: UUID) -> User | None: ...
    async def get_by_email(self, email: str) -> User | None: ...
    async def get_by_oauth_identity(
        self, provider: OAuthProvider, oauth_id: str
    ) -> User | None: ...
    async def create(self, user: User) -> User: ...
    async def link_oauth_identity(
        self, user_id: UUID, *, provider: OAuthProvider, oauth_id: str
    ) -> User: ...
    async def update_password(self, user_id: UUID, password_hash: str) -> User: ...


@runtime_checkable
class CredentialsRepository(Protocol):
    async def get_for_member(self, member_id: UUID) -> Credentials | None: ...
    async def get_by_oauth_identity(self, provider: str, oauth_id: str) -> Credentials | None: ...
    async def create(self, credentials: Credentials) -> Credentials: ...
    async def link_oauth_identity(
        self, member_id: UUID, provider: str, oauth_id: str
    ) -> Credentials: ...


@runtime_checkable
class WorkspaceRepository(Protocol):
    async def create(self, workspace: Workspace) -> Workspace: ...
    async def get_by_id(self, workspace_id: UUID) -> Workspace | None: ...


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

    def issue_selection_token(self, user: User) -> tuple[str, int]:
        """Short-lived token for the multi-workspace picker."""

    def decode_selection_token(self, token: str) -> UUID:
        """Verify a selection token and return the user_id sub."""
