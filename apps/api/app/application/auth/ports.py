from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from app.application.auth.oauth import OAuthIdentity
from app.domain.entities import Credentials, Member, User, Workspace
from app.domain.enums import OAuthProvider, TeamRole


@runtime_checkable
class MemberRepository(Protocol):
    async def get_by_email(self, email: str) -> Member | None: ...
    async def get_by_id(self, member_id: UUID) -> Member | None: ...
    async def list_by_ids(self, member_ids: list[UUID]) -> list[Member]: ...
    async def create(self, member: Member) -> Member: ...
    async def heartbeat(self, member_id: UUID) -> None: ...
    async def list_for_user(self, user_id: UUID) -> list[Member]: ...
    async def set_team(
        self,
        member_id: UUID,
        *,
        team_id: UUID | None,
        team_role: TeamRole | None,
    ) -> Member:
        """Assign / unassign a member to a team.

        Also used by ``DepartmentService`` to clear the team assignment
        of a member who is being promoted to Department Head — a Head
        sits above team-level leadership and shouldn't double-count as
        a team MANAGER/LEAD/MEMBER."""
        ...


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
    async def update_full_name(self, user_id: UUID, full_name: str) -> User: ...


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

    def issue_onboarding_token(self, identity: OAuthIdentity) -> tuple[str, int]:
        """Short-lived token for the SSO onboarding flow. Carries the
        OAuth identity but no DB ids — no User row exists yet."""

    def decode_onboarding_token(self, token: str) -> OAuthIdentity:
        """Verify an onboarding token and return the OAuth identity."""
