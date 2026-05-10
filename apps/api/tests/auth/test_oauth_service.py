"""OAuth login tests after the Phase 1 multi-tenancy split.

Resolution paths:
1. (provider, oauth_id) already known on a User -> log in.
2. Same email exists on a User -> link the OAuth identity to that user.
3. Brand new -> create User + Workspace + Member.

In all paths, the response shape is the new LoginResponse — single
membership returns access_token immediately, multi-membership returns
selection_token + workspaces.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.application.auth.oauth import OAuthIdentity
from app.application.auth.service import AuthService
from app.domain.entities import User, Workspace
from app.domain.enums import MemberType, OAuthProvider
from tests.auth.factories import make_human


def _identity(
    *,
    provider: OAuthProvider = OAuthProvider.GOOGLE,
    oauth_id: str = "google-sub-12345",
    email: str = "alice@kanea.ai",
    name: str = "Alice",
) -> OAuthIdentity:
    return OAuthIdentity(provider=provider, oauth_id=oauth_id, email=email, name=name)


def _user(email: str = "alice@kanea.ai", **kw) -> User:
    from datetime import UTC, datetime

    return User(
        id=uuid4(),
        email=email,
        full_name=kw.pop("full_name", "Alice"),
        password_hash=kw.pop("password_hash", "bcrypt$x"),
        oauth_provider=kw.pop("oauth_provider", None),
        oauth_id=kw.pop("oauth_id", None),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.fixture
def workspaces() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def members() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def credentials() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def users() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def hasher() -> MagicMock:
    h = MagicMock()
    h.hash.side_effect = lambda raw: f"bcrypt${raw}"
    return h


@pytest.fixture
def tokens() -> MagicMock:
    t = MagicMock()
    t.issue_human_token.return_value = ("human.jwt", 3600)
    t.issue_selection_token.return_value = ("selection.jwt", 300)
    return t


@pytest.fixture
def service(
    workspaces: AsyncMock,
    members: AsyncMock,
    credentials: AsyncMock,
    hasher: MagicMock,
    tokens: MagicMock,
    users: AsyncMock,
) -> AuthService:
    return AuthService(
        workspaces=workspaces,
        members=members,
        credentials=credentials,
        hasher=hasher,
        tokens=tokens,
        users=users,
    )


# Path 1: known oauth identity → log in.


async def test_oauth_login_known_identity_returns_token(
    service: AuthService,
    users: AsyncMock,
    members: AsyncMock,
    tokens: MagicMock,
) -> None:
    user = _user(oauth_provider=OAuthProvider.GOOGLE, oauth_id="google-sub-12345")
    users.get_by_oauth_identity.return_value = user
    membership = make_human(email=user.email)
    members.list_for_user.return_value = [membership]

    response = await service.oauth_login(_identity())

    assert response.requires_selection is False
    assert response.access_token == "human.jwt"
    users.get_by_oauth_identity.assert_awaited_once_with(OAuthProvider.GOOGLE, "google-sub-12345")
    tokens.issue_human_token.assert_called_once_with(membership)
    users.get_by_email.assert_not_called()


# Path 2: same email exists → link.


async def test_oauth_login_links_to_existing_email(
    service: AuthService,
    users: AsyncMock,
    members: AsyncMock,
    tokens: MagicMock,
) -> None:
    user = _user()
    membership = make_human(email=user.email)
    users.get_by_oauth_identity.return_value = None
    users.get_by_email.return_value = user
    users.link_oauth_identity.side_effect = lambda _id, **kw: user
    members.list_for_user.return_value = [membership]

    response = await service.oauth_login(_identity())

    assert response.access_token == "human.jwt"
    users.link_oauth_identity.assert_awaited_once_with(
        user.id, provider=OAuthProvider.GOOGLE, oauth_id="google-sub-12345"
    )


# Path 3: brand-new → provision.


async def test_oauth_login_provisions_new_account(
    service: AuthService,
    users: AsyncMock,
    workspaces: AsyncMock,
    members: AsyncMock,
    tokens: MagicMock,
) -> None:
    users.get_by_oauth_identity.return_value = None
    users.get_by_email.return_value = None
    users.create.side_effect = lambda u: u
    workspaces.create.side_effect = lambda ws: ws
    members.create.side_effect = lambda m: m
    members.list_for_user.return_value = [make_human(email="alice@kanea.ai")]

    response = await service.oauth_login(_identity())

    assert response.access_token == "human.jwt"
    users.create.assert_awaited_once()
    persisted_user: User = users.create.await_args.args[0]
    assert persisted_user.email == "alice@kanea.ai"
    assert persisted_user.oauth_provider is OAuthProvider.GOOGLE

    workspaces.create.assert_awaited_once()
    created_ws: Workspace = workspaces.create.await_args.args[0]
    assert created_ws.name == "Alice's workspace"

    members.create.assert_awaited_once()
    created_member = members.create.await_args.args[0]
    assert created_member.user_id == persisted_user.id
    assert created_member.type is MemberType.HUMAN


async def test_oauth_login_multi_workspace_returns_selection(
    service: AuthService,
    users: AsyncMock,
    members: AsyncMock,
    workspaces: AsyncMock,
    tokens: MagicMock,
) -> None:
    """If the OAuth user has more than one membership, the response is
    a selection token rather than a final access token."""
    user = _user(oauth_provider=OAuthProvider.GOOGLE, oauth_id="g-1")
    users.get_by_oauth_identity.return_value = user
    m1 = make_human(email=user.email)
    m2 = make_human(email=user.email)
    members.list_for_user.return_value = [m1, m2]
    from datetime import UTC, datetime

    workspaces.get_by_id.side_effect = lambda wid: Workspace(
        id=wid,
        name=f"WS {wid.hex[:4]}",
        slug="ws",
        task_prefix="WS",
        next_task_seq=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    response = await service.oauth_login(_identity())

    assert response.requires_selection is True
    assert response.selection_token == "selection.jwt"
    assert response.access_token is None
    tokens.issue_human_token.assert_not_called()
