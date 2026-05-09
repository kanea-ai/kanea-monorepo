"""NotificationService tests.

The service stitches three things: regex extraction (already covered
in test_mentions), member lookup by email-local-part, and writing one
Notification per resolved human. These tests pin the dedup + self-skip
behaviours and that we never resolve agents."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.application.notifications.service import NotificationService
from app.application.tasks.schemas import Principal
from app.domain.enums import MemberRole, MemberType, NotificationType
from tests.auth.factories import make_agent, make_human


def _principal(workspace_id=None, member_id=None) -> Principal:
    return Principal(
        member_id=member_id or uuid4(),
        workspace_id=workspace_id or uuid4(),
        type=MemberType.HUMAN,
        priority=1,
        scope="human",
        role=MemberRole.WORKSPACE_OWNER,
    )


@pytest.fixture
def notifications() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def members() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(notifications: AsyncMock, members: AsyncMock) -> NotificationService:
    return NotificationService(notifications=notifications, members=members)


async def test_no_mentions_writes_nothing(
    service: NotificationService, notifications: AsyncMock
) -> None:
    actor = _principal()
    written = await service.notify_mentions_in_task(
        body="just a plain description", task_id=uuid4(), actor=actor
    )
    assert written == 0
    notifications.create.assert_not_called()


async def test_creates_one_notification_per_resolved_human(
    service: NotificationService,
    notifications: AsyncMock,
    members: AsyncMock,
) -> None:
    actor = _principal()
    bob = make_human(workspace_id=actor.workspace_id, email="bob@kanea.ai", name="Bob")
    bob.user_id = uuid4()
    charlie = make_human(workspace_id=actor.workspace_id, email="charlie@kanea.ai", name="Charlie")
    charlie.user_id = uuid4()
    members.list_humans_by_email_locals.return_value = [bob, charlie]

    written = await service.notify_mentions_in_task(
        body="hey @bob and @charlie",
        task_id=uuid4(),
        actor=actor,
    )
    assert written == 2
    members.list_humans_by_email_locals.assert_awaited_once_with(
        actor.workspace_id, ["bob", "charlie"]
    )
    assert notifications.create.await_count == 2
    user_ids = {call.args[0].user_id for call in notifications.create.await_args_list}
    assert user_ids == {bob.user_id, charlie.user_id}
    types = {call.args[0].type for call in notifications.create.await_args_list}
    assert types == {NotificationType.MENTION_TASK}


async def test_skips_self_mentions(
    service: NotificationService, notifications: AsyncMock, members: AsyncMock
) -> None:
    """Pinging yourself is noise — drop self-mentions silently."""
    actor = _principal()
    self_member = make_human(member_id=actor.member_id, workspace_id=actor.workspace_id)
    self_member.user_id = uuid4()
    members.list_humans_by_email_locals.return_value = [self_member]

    written = await service.notify_mentions_in_task(
        body="@me note to self", task_id=uuid4(), actor=actor
    )
    assert written == 0
    notifications.create.assert_not_called()


async def test_agents_are_never_notified(
    service: NotificationService, notifications: AsyncMock, members: AsyncMock
) -> None:
    """The repo-side query already filters to HUMAN members; the
    service belt is treating any returned member without a user_id
    as unmentionable."""
    actor = _principal()
    bot = make_agent(workspace_id=actor.workspace_id)
    members.list_humans_by_email_locals.return_value = [bot]
    written = await service.notify_mentions_in_task(
        body="@bot run analysis", task_id=uuid4(), actor=actor
    )
    assert written == 0
    notifications.create.assert_not_called()


async def test_dedupes_when_same_user_holds_multiple_handles(
    service: NotificationService, notifications: AsyncMock, members: AsyncMock
) -> None:
    """Edge case: two member rows could share a user_id (across
    workspace forks during tests). One notification per user."""
    actor = _principal()
    same_user_id = uuid4()
    a = make_human(workspace_id=actor.workspace_id, email="alice@a.com")
    a.user_id = same_user_id
    b = make_human(workspace_id=actor.workspace_id, email="alice@b.com")
    b.user_id = same_user_id
    members.list_humans_by_email_locals.return_value = [a, b]

    written = await service.notify_mentions_in_task(body="hey @alice", task_id=uuid4(), actor=actor)
    assert written == 1
    assert notifications.create.await_count == 1


async def test_comment_uses_mention_comment_type(
    service: NotificationService, notifications: AsyncMock, members: AsyncMock
) -> None:
    actor = _principal()
    bob = make_human(workspace_id=actor.workspace_id, email="bob@kanea.ai")
    bob.user_id = uuid4()
    members.list_humans_by_email_locals.return_value = [bob]

    written = await service.notify_mentions_in_comment(
        body="@bob ping",
        task_id=uuid4(),
        comment_id=uuid4(),
        actor=actor,
    )
    assert written == 1
    persisted = notifications.create.await_args.args[0]
    assert persisted.type is NotificationType.MENTION_COMMENT
    assert persisted.source_comment_id is not None
