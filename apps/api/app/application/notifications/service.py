from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.application.notifications.mentions import extract_handles
from app.application.notifications.ports import (
    MentionMemberLookup,
    NotificationRepository,
)
from app.application.tasks.schemas import Principal
from app.domain.entities import Notification
from app.domain.enums import NotificationType


def _preview(text: str | None, *, limit: int = 280) -> str:
    """Trim a body to a one-line, length-capped preview suitable for
    the notification bell. We keep newlines as spaces — preview rows
    get one line of vertical space."""
    if not text:
        return ""
    flat = " ".join(text.split())
    if len(flat) <= limit:
        return flat
    return flat[: limit - 1].rstrip() + "…"


@dataclass(slots=True)
class NotificationService:
    notifications: NotificationRepository
    members: MentionMemberLookup

    async def notify_mentions_in_task(
        self,
        *,
        body: str | None,
        task_id: UUID,
        actor: Principal,
    ) -> int:
        """Scan a task description for @mentions and create a
        MENTION_TASK notification per resolved human. Returns the count
        actually written (deduped, self-mentions skipped)."""
        return await self._notify(
            body=body,
            actor=actor,
            kind=NotificationType.MENTION_TASK,
            task_id=task_id,
            comment_id=None,
        )

    async def notify_mentions_in_comment(
        self,
        *,
        body: str | None,
        task_id: UUID,
        comment_id: UUID,
        actor: Principal,
    ) -> int:
        return await self._notify(
            body=body,
            actor=actor,
            kind=NotificationType.MENTION_COMMENT,
            task_id=task_id,
            comment_id=comment_id,
        )

    async def notify_cross_team_request(
        self,
        *,
        recipient_user_ids: list[UUID],
        actor: Principal,
        target_task_id: UUID,
        preview: str,
    ) -> int:
        """Write a CROSS_TEAM_REQUEST notification row per recipient.

        Policy (who-to-notify) lives in TaskService.create_request,
        which assembles the recipient list from the target team's
        leadership + dept head — already excluding the requester and
        non-HUMAN members — with a workspace-owner fallback for
        leaderless teams. This method is the thin mechanism: dedup
        the caller-supplied list, write the rows. Returns the count
        written.

        ``target_task_id`` is the *newly minted* target task (where
        the recipient's triage action — delegate / cancel / let it
        sit — happens). Deep-linking the bell row to this task lands
        the recipient on the detail page with the Delegate control
        immediately visible.
        """
        seen: set[UUID] = set()
        written = 0
        for user_id in recipient_user_ids:
            if user_id in seen:
                continue
            seen.add(user_id)
            await self.notifications.create(
                Notification(
                    id=uuid4(),
                    user_id=user_id,
                    type=NotificationType.CROSS_TEAM_REQUEST,
                    source_task_id=target_task_id,
                    source_comment_id=None,
                    source_member_id=actor.member_id,
                    preview=_preview(preview),
                    read_at=None,
                    created_at=datetime.now(UTC),
                )
            )
            written += 1
        return written

    async def _notify(
        self,
        *,
        body: str | None,
        actor: Principal,
        kind: NotificationType,
        task_id: UUID,
        comment_id: UUID | None,
    ) -> int:
        handles = extract_handles(body)
        if not handles:
            return 0
        targets = await self.members.list_humans_by_email_locals(actor.workspace_id, handles)
        # Skip self-mentions — pinging yourself is just noise.
        targets = [m for m in targets if m.id != actor.member_id and m.user_id is not None]
        if not targets:
            return 0

        preview = _preview(body)
        seen_user_ids: set[UUID] = set()
        written = 0
        for member in targets:
            assert member.user_id is not None  # checked above
            if member.user_id in seen_user_ids:
                continue
            seen_user_ids.add(member.user_id)
            await self.notifications.create(
                Notification(
                    id=uuid4(),
                    user_id=member.user_id,
                    type=kind,
                    source_task_id=task_id,
                    source_comment_id=comment_id,
                    source_member_id=actor.member_id,
                    preview=preview,
                    read_at=None,
                    created_at=datetime.now(UTC),
                )
            )
            written += 1
        return written
