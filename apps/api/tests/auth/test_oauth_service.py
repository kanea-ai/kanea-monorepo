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
from app.domain.enums import OAuthProvider
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
def agent_api_keys() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(
    workspaces: AsyncMock,
    members: AsyncMock,
    credentials: AsyncMock,
    hasher: MagicMock,
    tokens: MagicMock,
    users: AsyncMock,
    agent_api_keys: AsyncMock,
) -> AuthService:
    return AuthService(
        workspaces=workspaces,
        members=members,
        credentials=credentials,
        hasher=hasher,
        tokens=tokens,
        agent_api_keys=agent_api_keys,
        agent_api_key_env_tag="dev",  # pragma: allowlist secret
        agent_api_key_pepper="test-pepper",  # pragma: allowlist secret
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


# Path 3: brand-new → onboarding (deferred provisioning, was auto-provision pre-Task-3).
#
# As of Task 3, a brand-new OAuth user is NOT auto-provisioned. The
# service mints an onboarding token carrying the OAuth identity and
# returns ``requires_onboarding=True``; the frontend prompts for a
# workspace name and POSTs to ``/auth/complete-oauth-onboarding`` to
# finish the signup. No DB rows are created in oauth_login for
# brand-new users — that path moved to complete_oauth_onboarding.


async def test_oauth_login_brand_new_returns_onboarding_token(
    service: AuthService,
    users: AsyncMock,
    workspaces: AsyncMock,
    members: AsyncMock,
    tokens: MagicMock,
) -> None:
    tokens.issue_onboarding_token.return_value = ("onboarding.jwt", 600)
    users.get_by_oauth_identity.return_value = None
    users.get_by_email.return_value = None

    response = await service.oauth_login(_identity())

    # Onboarding branch: no token, no DB writes.
    assert response.requires_onboarding is True
    assert response.onboarding_token == "onboarding.jwt"
    assert response.access_token is None
    assert response.requires_selection is False
    # The suggested name preview lets the FE prefill the prompt.
    assert response.suggested_workspace_name == "Alice's workspace"

    # No User / Workspace / Member created yet — that happens in
    # complete_oauth_onboarding.
    users.create.assert_not_called()
    workspaces.create.assert_not_called()
    members.create.assert_not_called()
    # Onboarding token was issued with the OAuth identity payload.
    tokens.issue_onboarding_token.assert_called_once()
    issued_identity = tokens.issue_onboarding_token.call_args.args[0]
    assert issued_identity.email == "alice@kanea.ai"
    assert issued_identity.provider is OAuthProvider.GOOGLE


async def test_oauth_login_brand_new_no_name_falls_back_to_workspace(
    service: AuthService,
    users: AsyncMock,
    tokens: MagicMock,
) -> None:
    """When the OAuth identity has no display name, the suggested
    workspace name falls back to a sensible default ('Workspace')
    rather than including a None."""
    tokens.issue_onboarding_token.return_value = ("onboarding.jwt", 600)
    users.get_by_oauth_identity.return_value = None
    users.get_by_email.return_value = None

    response = await service.oauth_login(
        _identity(name=None, email="anon@example.com")  # type: ignore[arg-type]
    )
    assert response.requires_onboarding is True
    assert response.suggested_workspace_name == "Workspace"


# complete_oauth_onboarding: the second leg of the brand-new path.


async def test_complete_oauth_onboarding_creates_account(
    service: AuthService,
    users: AsyncMock,
    workspaces: AsyncMock,
    members: AsyncMock,
    tokens: MagicMock,
) -> None:
    tokens.decode_onboarding_token.return_value = _identity()
    users.get_by_oauth_identity.return_value = None
    users.get_by_email.return_value = None
    users.create.side_effect = lambda u: u
    workspaces.create.side_effect = lambda ws: ws
    members.create.side_effect = lambda m: m
    new_member = make_human(email="alice@kanea.ai")
    members.list_for_user.return_value = [new_member]

    response = await service.complete_oauth_onboarding(
        onboarding_token="onboarding.jwt",
        workspace_name="Acme",
    )

    # Trio of writes happens here, NOT in oauth_login.
    users.create.assert_awaited_once()
    persisted_user: User = users.create.await_args.args[0]
    assert persisted_user.email == "alice@kanea.ai"
    assert persisted_user.oauth_provider is OAuthProvider.GOOGLE

    workspaces.create.assert_awaited_once()
    created_ws: Workspace = workspaces.create.await_args.args[0]
    # Critically: the workspace takes the USER-PROVIDED name, NOT the
    # auto-generated "{full_name}'s workspace" template.
    assert created_ws.name == "Acme"

    members.create.assert_awaited_once()
    created_member = members.create.await_args.args[0]
    assert created_member.user_id == persisted_user.id

    assert response.access_token == "human.jwt"


async def test_complete_oauth_onboarding_invalid_token_raises(
    service: AuthService,
    tokens: MagicMock,
    users: AsyncMock,
) -> None:
    """Expired / malformed / wrong-scope onboarding tokens surface as
    AuthenticationError (mapped to 401 at the route)."""
    import jwt as pyjwt

    from app.domain.exceptions import AuthenticationError

    tokens.decode_onboarding_token.side_effect = pyjwt.InvalidTokenError("expired")
    with pytest.raises(AuthenticationError):
        await service.complete_oauth_onboarding(onboarding_token="bad.jwt", workspace_name="Acme")
    users.create.assert_not_called()


async def test_complete_oauth_onboarding_name_conflict_raises(
    service: AuthService,
    users: AsyncMock,
    workspaces: AsyncMock,
    tokens: MagicMock,
) -> None:
    """Globally-unique workspaces.name: a taken name on the platform
    surfaces as WorkspaceNameConflictError (mapped to 409)."""
    from sqlalchemy.exc import IntegrityError

    from app.domain.exceptions import WorkspaceNameConflictError

    tokens.decode_onboarding_token.return_value = _identity()
    users.get_by_oauth_identity.return_value = None
    users.get_by_email.return_value = None
    users.create.side_effect = lambda u: u
    workspaces.create.side_effect = IntegrityError("unique", params=None, orig=Exception())

    with pytest.raises(WorkspaceNameConflictError):
        await service.complete_oauth_onboarding(
            onboarding_token="onboarding.jwt", workspace_name="Taken"
        )


async def test_complete_oauth_onboarding_already_signed_up_returns_token(
    service: AuthService,
    users: AsyncMock,
    workspaces: AsyncMock,
    members: AsyncMock,
    tokens: MagicMock,
) -> None:
    """Race condition: between oauth_login (which minted the token)
    and complete (which is being called now), the user finished
    signup via a different tab. We don't double-provision — we just
    log them in to their existing workspace."""
    tokens.decode_onboarding_token.return_value = _identity()
    existing_user = _user(oauth_provider=OAuthProvider.GOOGLE, oauth_id="google-sub-12345")
    users.get_by_oauth_identity.return_value = existing_user
    members.list_for_user.return_value = [make_human(email=existing_user.email)]

    response = await service.complete_oauth_onboarding(
        onboarding_token="onboarding.jwt", workspace_name="Whatever"
    )
    assert response.access_token == "human.jwt"
    users.create.assert_not_called()
    workspaces.create.assert_not_called()


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
