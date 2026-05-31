"""Phase 5 batch 1 — workspace switcher backend tests.

Three new flows:
- list_my_workspaces (sidebar dropdown / /workspaces page)
- create_my_workspace (the "+" in the dropdown)
- AuthService.switch_workspace (instant switch from the dropdown)
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.application.auth.schemas import SwitchWorkspaceRequest
from app.application.auth.service import AuthService
from app.application.me.schemas import CreateMyWorkspaceRequest
from app.application.me.service import MeService
from app.application.tasks.schemas import Principal
from app.domain.entities import User, Workspace
from app.domain.enums import MemberRole, MemberType
from app.domain.exceptions import (
    AuthenticationError,
    InvalidMemberTypeError,
    WorkspaceNameConflictError,
)
from tests.auth.factories import make_human


def _principal(*, member_id=None, workspace_id=None) -> Principal:
    return Principal(
        member_id=member_id or uuid4(),
        workspace_id=workspace_id or uuid4(),
        type=MemberType.HUMAN,
        priority=1,
        scope="human",
        role=MemberRole.WORKSPACE_OWNER,
    )


def _user(**kw) -> User:
    now = datetime.now(UTC)
    return User(
        id=kw.pop("id", uuid4()),
        email=kw.pop("email", "alice@kanea.ai"),
        full_name=kw.pop("full_name", "Alice"),
        password_hash="bcrypt$x",  # pragma: allowlist secret
        created_at=now,
        updated_at=now,
    )


def _ws(name: str) -> Workspace:
    now = datetime.now(UTC)
    return Workspace(
        id=uuid4(),
        name=name,
        slug=name.lower(),
        task_prefix=name[:4].upper(),
        next_task_seq=1,
        created_at=now,
        updated_at=now,
    )


# ---------- list_my_workspaces ----------


@pytest.fixture
def me_service() -> tuple[MeService, AsyncMock, AsyncMock, AsyncMock, MagicMock, MagicMock]:
    users = AsyncMock()
    members = AsyncMock()
    workspaces = AsyncMock()
    hasher = MagicMock()
    tokens = MagicMock()
    tokens.issue_human_token.return_value = ("new.jwt", 3600)
    svc = MeService(
        users=users,
        members=members,
        workspaces=workspaces,
        hasher=hasher,
        tokens=tokens,
    )
    return svc, users, members, workspaces, hasher, tokens


async def test_list_my_workspaces_marks_current(
    me_service: tuple[MeService, AsyncMock, AsyncMock, AsyncMock, MagicMock, MagicMock],
) -> None:
    svc, _users, members, workspaces, _h, _t = me_service
    p = _principal()
    user_id = uuid4()

    self_member = make_human(member_id=p.member_id, workspace_id=p.workspace_id)
    self_member.user_id = user_id
    other_member = make_human(workspace_id=uuid4())
    other_member.user_id = user_id

    members.get_by_id.return_value = self_member
    members.list_for_user.return_value = [self_member, other_member]
    ws_a = _ws("Acme")
    ws_b = _ws("Beta")

    async def get_by_id(wid):
        if wid == self_member.workspace_id:
            return Workspace(
                id=wid,
                name=ws_a.name,
                slug=ws_a.slug,
                task_prefix=ws_a.task_prefix,
                next_task_seq=1,
                created_at=ws_a.created_at,
                updated_at=ws_a.updated_at,
            )
        return Workspace(
            id=wid,
            name=ws_b.name,
            slug=ws_b.slug,
            task_prefix=ws_b.task_prefix,
            next_task_seq=1,
            created_at=ws_b.created_at,
            updated_at=ws_b.updated_at,
        )

    workspaces.get_by_id.side_effect = get_by_id

    out = await svc.list_my_workspaces(p)
    assert len(out) == 2
    # Current first.
    assert out[0].is_current is True
    assert out[0].workspace_id == self_member.workspace_id
    assert out[1].is_current is False


async def test_list_my_workspaces_404s_when_member_missing(
    me_service: tuple[MeService, AsyncMock, AsyncMock, AsyncMock, MagicMock, MagicMock],
) -> None:
    svc, _u, members, _w, _h, _t = me_service
    members.get_by_id.return_value = None
    with pytest.raises(InvalidMemberTypeError):
        await svc.list_my_workspaces(_principal())


# ---------- create_my_workspace ----------


async def test_create_my_workspace_mints_owner_membership(
    me_service: tuple[MeService, AsyncMock, AsyncMock, AsyncMock, MagicMock, MagicMock],
) -> None:
    svc, users, members, workspaces, _h, tokens = me_service
    p = _principal()
    user = _user()
    self_member = make_human(member_id=p.member_id, workspace_id=p.workspace_id)
    self_member.user_id = user.id
    members.get_by_id.return_value = self_member
    users.get_by_id.return_value = user
    workspaces.create.side_effect = lambda ws: ws
    members.create.side_effect = lambda m: m

    out = await svc.create_my_workspace(p, CreateMyWorkspaceRequest(name="New Co"))
    assert out.access_token == "new.jwt"
    assert out.expires_in == 3600
    workspaces.create.assert_awaited_once()
    new_ws = workspaces.create.await_args.args[0]
    assert new_ws.name == "New Co"
    members.create.assert_awaited_once()
    new_member = members.create.await_args.args[0]
    assert new_member.user_id == user.id
    assert new_member.role is MemberRole.WORKSPACE_OWNER
    tokens.issue_human_token.assert_called_once_with(new_member)


async def test_create_my_workspace_409s_on_duplicate_name(
    me_service: tuple[MeService, AsyncMock, AsyncMock, AsyncMock, MagicMock, MagicMock],
) -> None:
    from sqlalchemy.exc import IntegrityError

    svc, users, members, workspaces, _h, _t = me_service
    p = _principal()
    user = _user()
    self_member = make_human(member_id=p.member_id, workspace_id=p.workspace_id)
    self_member.user_id = user.id
    members.get_by_id.return_value = self_member
    users.get_by_id.return_value = user
    workspaces.create.side_effect = IntegrityError("INSERT", {}, Exception("uniq"))

    with pytest.raises(WorkspaceNameConflictError):
        await svc.create_my_workspace(p, CreateMyWorkspaceRequest(name="Existing"))


# ---------- AuthService.switch_workspace ----------


@pytest.fixture
def auth_service() -> (
    tuple[AuthService, AsyncMock, AsyncMock, AsyncMock, MagicMock, MagicMock, AsyncMock]
):
    workspaces = AsyncMock()
    members = AsyncMock()
    credentials = AsyncMock()
    hasher = MagicMock()
    tokens = MagicMock()
    tokens.issue_human_token.return_value = ("switch.jwt", 3600)
    users = AsyncMock()
    svc = AuthService(
        workspaces=workspaces,
        members=members,
        credentials=credentials,
        hasher=hasher,
        tokens=tokens,
        agent_api_keys=AsyncMock(),
        agent_api_key_env_tag="dev",  # pragma: allowlist secret
        agent_api_key_pepper="test-pepper",  # pragma: allowlist secret
        users=users,
    )
    return svc, workspaces, members, credentials, hasher, tokens, users


async def test_switch_workspace_happy_path(
    auth_service: tuple[
        AuthService, AsyncMock, AsyncMock, AsyncMock, MagicMock, MagicMock, AsyncMock
    ],
) -> None:
    svc, _w, members, _c, _h, tokens, _u = auth_service
    user_id = uuid4()
    current = make_human()
    current.user_id = user_id
    target = make_human(workspace_id=uuid4())
    target.user_id = user_id
    members.get_by_id.return_value = current
    members.list_for_user.return_value = [current, target]

    out = await svc.switch_workspace(
        _principal(member_id=current.id, workspace_id=current.workspace_id),
        SwitchWorkspaceRequest(workspace_id=target.workspace_id),
    )
    assert out.access_token == "switch.jwt"
    tokens.issue_human_token.assert_called_once_with(target)


async def test_switch_workspace_rejects_non_member(
    auth_service: tuple[
        AuthService, AsyncMock, AsyncMock, AsyncMock, MagicMock, MagicMock, AsyncMock
    ],
) -> None:
    svc, _w, members, _c, _h, _t, _u = auth_service
    current = make_human()
    current.user_id = uuid4()
    members.get_by_id.return_value = current
    members.list_for_user.return_value = [current]

    with pytest.raises(AuthenticationError):
        await svc.switch_workspace(
            _principal(member_id=current.id, workspace_id=current.workspace_id),
            SwitchWorkspaceRequest(workspace_id=uuid4()),
        )


async def test_switch_workspace_rejects_when_self_member_missing(
    auth_service: tuple[
        AuthService, AsyncMock, AsyncMock, AsyncMock, MagicMock, MagicMock, AsyncMock
    ],
) -> None:
    svc, _w, members, _c, _h, _t, _u = auth_service
    members.get_by_id.return_value = None
    with pytest.raises(AuthenticationError):
        await svc.switch_workspace(_principal(), SwitchWorkspaceRequest(workspace_id=uuid4()))
