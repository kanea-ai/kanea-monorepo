"""MeService tests — Phase 2 self-profile endpoints.

Covers:
- get_profile combines User + Member + Workspace into the response
- update_profile renames the User row, not the Member projection
- change_password verifies the current password before swapping
- change_password rejects OAuth-only users (no password to verify against)
- get_stats reuses compute_agent_stats and projects to MeStatsResponse
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.application.me.schemas import (
    ChangePasswordRequest,
    UpdateMeRequest,
)
from app.application.me.service import MeService
from app.application.tasks.schemas import Principal
from app.domain.entities import AgentStats, User, Workspace
from app.domain.enums import MemberRole, MemberType
from app.domain.exceptions import AuthenticationError, InvalidMemberTypeError
from tests.auth.factories import make_human


def _principal(*, member_id=None, workspace_id=None) -> Principal:
    return Principal(
        member_id=member_id or uuid4(),
        workspace_id=workspace_id or uuid4(),
        type=MemberType.HUMAN,
        priority=5,
        scope="human",
        role=MemberRole.WORKSPACE_USER,
    )


def _user(**kw) -> User:
    now = datetime.now(UTC)
    return User(
        id=kw.pop("id", uuid4()),
        email=kw.pop("email", "alice@kanea.ai"),
        full_name=kw.pop("full_name", "Alice"),
        password_hash=kw.pop("password_hash", "bcrypt$x"),  # pragma: allowlist secret
        oauth_provider=kw.pop("oauth_provider", None),
        oauth_id=kw.pop("oauth_id", None),
        created_at=now,
        updated_at=now,
    )


def _workspace(name: str = "Acme") -> Workspace:
    now = datetime.now(UTC)
    return Workspace(
        id=uuid4(),
        name=name,
        slug="acme-abc123",
        task_prefix="ACME",
        next_task_seq=1,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def users() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def members() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def workspaces() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def hasher() -> MagicMock:
    h = MagicMock()
    h.verify.return_value = True
    h.hash.side_effect = lambda raw: f"bcrypt${raw}"
    return h


@pytest.fixture
def service(
    users: AsyncMock,
    members: AsyncMock,
    workspaces: AsyncMock,
    hasher: MagicMock,
) -> MeService:
    return MeService(users=users, members=members, workspaces=workspaces, hasher=hasher)


# ---------- get_profile ----------


async def test_get_profile_combines_user_member_workspace(
    service: MeService,
    users: AsyncMock,
    members: AsyncMock,
    workspaces: AsyncMock,
) -> None:
    p = _principal()
    user = _user()
    member = make_human(member_id=p.member_id, workspace_id=p.workspace_id)
    member.user_id = user.id
    member.role = MemberRole.WORKSPACE_ADMIN
    members.get_by_id.return_value = member
    users.get_by_id.return_value = user
    ws = _workspace("Acme")
    workspaces.get_by_id.return_value = ws

    out = await service.get_profile(p)
    assert out.user_id == user.id
    assert out.email == user.email
    assert out.full_name == user.full_name
    assert out.has_password is True
    assert out.workspace_id == ws.id
    assert out.workspace_name == "Acme"
    assert out.role is MemberRole.WORKSPACE_ADMIN


async def test_get_profile_404_when_member_missing(service: MeService, members: AsyncMock) -> None:
    members.get_by_id.return_value = None
    with pytest.raises(InvalidMemberTypeError):
        await service.get_profile(_principal())


async def test_get_profile_404_when_member_in_other_workspace(
    service: MeService, members: AsyncMock
) -> None:
    p = _principal()
    foreign = make_human(member_id=p.member_id)  # different workspace_id
    members.get_by_id.return_value = foreign
    with pytest.raises(InvalidMemberTypeError):
        await service.get_profile(p)


# ---------- update_profile ----------


async def test_update_profile_renames_user(
    service: MeService,
    users: AsyncMock,
    members: AsyncMock,
    workspaces: AsyncMock,
) -> None:
    p = _principal()
    user = _user(full_name="Old")
    member = make_human(member_id=p.member_id, workspace_id=p.workspace_id)
    member.user_id = user.id
    members.get_by_id.return_value = member
    # Second get_by_id call lands inside the get_profile re-fetch.
    users.get_by_id.return_value = user
    workspaces.get_by_id.return_value = _workspace()
    users.update_full_name.return_value = user

    await service.update_profile(p, UpdateMeRequest(full_name="New"))
    users.update_full_name.assert_awaited_once_with(user.id, "New")


# ---------- change_password ----------


async def test_change_password_happy_path(
    service: MeService,
    users: AsyncMock,
    members: AsyncMock,
    hasher: MagicMock,
) -> None:
    p = _principal()
    user = _user(password_hash="bcrypt$old")  # pragma: allowlist secret
    member = make_human(member_id=p.member_id, workspace_id=p.workspace_id)
    member.user_id = user.id
    members.get_by_id.return_value = member
    users.get_by_id.return_value = user

    await service.change_password(
        p,
        ChangePasswordRequest(
            current_password="oldpwd",  # pragma: allowlist secret
            new_password="brandnew1!",  # pragma: allowlist secret
        ),
    )
    hasher.verify.assert_called_once_with("oldpwd", "bcrypt$old")
    users.update_password.assert_awaited_once_with(user.id, "bcrypt$brandnew1!")


async def test_change_password_rejects_wrong_current(
    service: MeService,
    users: AsyncMock,
    members: AsyncMock,
    hasher: MagicMock,
) -> None:
    p = _principal()
    user = _user(password_hash="bcrypt$old")  # pragma: allowlist secret
    member = make_human(member_id=p.member_id, workspace_id=p.workspace_id)
    member.user_id = user.id
    members.get_by_id.return_value = member
    users.get_by_id.return_value = user
    hasher.verify.return_value = False

    with pytest.raises(AuthenticationError):
        await service.change_password(
            p,
            ChangePasswordRequest(
                current_password="wrong",  # pragma: allowlist secret
                new_password="brandnew1!",  # pragma: allowlist secret
            ),
        )
    users.update_password.assert_not_called()


async def test_change_password_rejects_oauth_only_user(
    service: MeService,
    users: AsyncMock,
    members: AsyncMock,
) -> None:
    p = _principal()
    user = _user(password_hash=None, oauth_provider=None)
    member = make_human(member_id=p.member_id, workspace_id=p.workspace_id)
    member.user_id = user.id
    members.get_by_id.return_value = member
    users.get_by_id.return_value = user

    with pytest.raises(AuthenticationError, match="password not set"):
        await service.change_password(
            p,
            ChangePasswordRequest(
                current_password="anything",  # pragma: allowlist secret
                new_password="brandnew1!",  # pragma: allowlist secret
            ),
        )


# ---------- get_stats ----------


async def test_get_stats_projects_member_stats(service: MeService, members: AsyncMock) -> None:
    p = _principal()
    members.compute_agent_stats.return_value = AgentStats(
        assigned_count=3,
        completed_count=10,
        avg_resolution_seconds=1234.5,
        accuracy_percent=4.2,
        last_activity_at=datetime.now(UTC),
        total_tokens_used=42,
    )
    out = await service.get_stats(p)
    assert out.assigned_count == 3
    assert out.completed_count == 10
    assert out.avg_resolution_seconds == 1234.5
    assert out.total_tokens_used == 42
    members.compute_agent_stats.assert_awaited_once_with(p.member_id)
