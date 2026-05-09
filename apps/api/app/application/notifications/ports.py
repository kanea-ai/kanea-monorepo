from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from app.domain.entities import Member, Notification


@runtime_checkable
class NotificationRepository(Protocol):
    async def create(self, notification: Notification) -> Notification: ...
    async def list_for_user(
        self, user_id: UUID, *, limit: int = 50, offset: int = 0
    ) -> list[Notification]: ...
    async def unread_count(self, user_id: UUID) -> int: ...
    async def mark_read(self, notification_id: UUID, user_id: UUID) -> int: ...
    async def mark_all_read(self, user_id: UUID) -> int: ...


@runtime_checkable
class MentionMemberLookup(Protocol):
    """Reads the workspace's HUMAN members by email-local-part — the
    bridge from a `@handle` token in a comment body to a concrete
    user_id we can drop a notification on."""

    async def list_humans_by_email_locals(
        self, workspace_id: UUID, locals_lc: list[str]
    ) -> list[Member]: ...
