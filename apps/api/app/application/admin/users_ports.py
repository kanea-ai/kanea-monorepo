from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID

from app.domain.entities import User
from app.domain.enums import MemberRole


@dataclass(slots=True)
class UserRowWithWorkspaceCount:
    user: User
    workspace_count: int


@dataclass(slots=True)
class AdminMembershipRow:
    workspace_id: UUID
    workspace_name: str
    workspace_slug: str
    member_id: UUID
    role: MemberRole
    is_suspended: bool


@runtime_checkable
class AdminUserRepository(Protocol):
    """Cross-tenant user surface served to the back-office. Read paths
    join ``members`` + ``workspaces`` so a single round-trip carries
    the per-workspace membership grid."""

    async def list_users(
        self,
        *,
        name: str | None = None,
        skip: int = 0,
        limit: int = 25,
    ) -> tuple[list[UserRowWithWorkspaceCount], int]: ...

    async def get_user(self, user_id: UUID) -> User | None: ...

    async def list_memberships_for_user(self, user_id: UUID) -> list[AdminMembershipRow]: ...

    async def set_banned(self, user_id: UUID, *, is_banned: bool) -> User: ...

    async def force_reset(
        self,
        user_id: UUID,
        *,
        new_password_hash: str,
        sessions_invalidated_at: datetime,
    ) -> User: ...
