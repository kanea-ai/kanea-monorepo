from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.auth.oauth import OAuthIdentity
from app.application.auth.service import AuthService
from app.domain.enums import MemberType, OAuthProvider
from tests.auth.factories import make_agent, make_credentials, make_human


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
def hasher() -> MagicMock:
    h = MagicMock()
    h.hash.side_effect = lambda raw: f"bcrypt${raw}"
    return h


@pytest.fixture
def tokens() -> MagicMock:
    t = MagicMock()
    t.issue_human_token.return_value = ("human.jwt", 3600)
    return t


@pytest.fixture
def service(
    workspaces: AsyncMock,
    members: AsyncMock,
    credentials: AsyncMock,
    hasher: MagicMock,
    tokens: MagicMock,
) -> AuthService:
    return AuthService(
        workspaces=workspaces,
        members=members,
        credentials=credentials,
        hasher=hasher,
        tokens=tokens,
    )


def _identity(
    *,
    provider: OAuthProvider = OAuthProvider.GOOGLE,
    oauth_id: str = "google-sub-12345",
    email: str = "alice@kanea.ai",
    name: str = "Alice",
) -> OAuthIdentity:
    return OAuthIdentity(provider=provider, oauth_id=oauth_id, email=email, name=name)


# Resolution path 1: known oauth identity -> log in.


async def test_oauth_login_known_identity_returns_token(
    service: AuthService,
    members: AsyncMock,
    credentials: AsyncMock,
    tokens: MagicMock,
) -> None:
    human = make_human(email="alice@kanea.ai")
    credentials.get_by_oauth_identity.return_value = make_credentials(
        member_id=human.id,
        password_hash=None,
    )
    members.get_by_id.return_value = human

    response = await service.oauth_login(_identity())

    assert response.access_token == "human.jwt"
    credentials.get_by_oauth_identity.assert_awaited_once_with("GOOGLE", "google-sub-12345")
    tokens.issue_human_token.assert_called_once_with(human)
    # Didn't fall through to email lookup or new-account creation.
    members.get_by_email.assert_not_called()
    credentials.create.assert_not_called()


# Resolution path 2: same email already exists -> link identity, log in.


async def test_oauth_login_links_to_existing_email(
    service: AuthService,
    members: AsyncMock,
    credentials: AsyncMock,
    tokens: MagicMock,
) -> None:
    human = make_human(email="alice@kanea.ai")
    credentials.get_by_oauth_identity.return_value = None
    members.get_by_email.return_value = human

    response = await service.oauth_login(_identity())

    assert response.access_token == "human.jwt"
    credentials.link_oauth_identity.assert_awaited_once_with(human.id, "GOOGLE", "google-sub-12345")
    tokens.issue_human_token.assert_called_once_with(human)
    # No new workspace / member.
    members.create.assert_not_called()
    credentials.create.assert_not_called()


async def test_oauth_login_rejects_email_owned_by_agent(
    service: AuthService,
    members: AsyncMock,
    credentials: AsyncMock,
) -> None:
    """If an AGENT-typed member somehow shares the OAuth email, we refuse
    rather than log them in or link an OAuth identity onto an agent."""
    credentials.get_by_oauth_identity.return_value = None
    members.get_by_email.return_value = make_agent()

    from app.domain.exceptions import AuthenticationError

    with pytest.raises(AuthenticationError):
        await service.oauth_login(_identity())


# Resolution path 3: brand-new -> provision workspace + member + credentials.


async def test_oauth_login_provisions_new_account(
    service: AuthService,
    workspaces: AsyncMock,
    members: AsyncMock,
    credentials: AsyncMock,
    tokens: MagicMock,
) -> None:
    credentials.get_by_oauth_identity.return_value = None
    members.get_by_email.return_value = None
    workspaces.create.side_effect = lambda ws: ws
    members.create.side_effect = lambda m: m
    credentials.create.side_effect = lambda c: c

    response = await service.oauth_login(_identity(name="Alice", email="alice@kanea.ai"))

    assert response.access_token == "human.jwt"

    workspaces.create.assert_awaited_once()
    created_ws = workspaces.create.await_args.args[0]
    assert created_ws.name == "Alice's workspace"

    members.create.assert_awaited_once()
    created_member = members.create.await_args.args[0]
    assert created_member.workspace_id == created_ws.id
    assert created_member.type is MemberType.HUMAN
    assert created_member.priority == 1
    assert created_member.email == "alice@kanea.ai"
    assert created_member.name == "Alice"

    credentials.create.assert_awaited_once()
    created_creds = credentials.create.await_args.args[0]
    assert created_creds.member_id == created_member.id
    assert created_creds.password_hash is None
    assert created_creds.oauth_provider is OAuthProvider.GOOGLE
    assert created_creds.oauth_id == "google-sub-12345"
