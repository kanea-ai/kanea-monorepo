"""AuthService tests after the Phase 1 multi-tenancy split.

Auth identity now lives on the global `users` table; `members` is the
per-workspace projection. Login looks up by email on users, verifies
the password, then enumerates memberships:

- 0 memberships -> AuthenticationError
- 1 membership -> normal access token
- >1 memberships -> selection token + workspace list
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import jwt
import pytest

from app.application.auth.schemas import (
    AgentTokenRequest,
    LoginRequest,
    RegisterRequest,
    SelectWorkspaceRequest,
)
from app.application.auth.service import AuthService
from app.domain.entities import User, Workspace
from app.domain.enums import MemberType
from app.domain.exceptions import AuthenticationError, EmailAlreadyExistsError
from tests.auth.factories import make_agent, make_credentials, make_human


def _user(email: str = "alice@kanea.ai") -> User:
    now = datetime.now(UTC)
    return User(
        id=uuid4(),
        email=email,
        full_name="Alice",
        password_hash="bcrypt$hash",  # pragma: allowlist secret
        created_at=now,
        updated_at=now,
    )


def _workspace(name: str = "Acme") -> Workspace:
    now = datetime.now(UTC)
    return Workspace(
        id=uuid4(),
        name=name,
        slug=f"{name.lower()}-abc123",
        task_prefix="ACME",
        next_task_seq=1,
        created_at=now,
        updated_at=now,
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
    h.verify.return_value = True
    h.hash.side_effect = lambda raw: f"bcrypt${raw}"
    return h


@pytest.fixture
def tokens() -> MagicMock:
    t = MagicMock()
    t.issue_human_token.return_value = ("human.jwt", 3600)
    t.issue_agent_token.return_value = ("agent.jwt", 900)
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


# ---------- login ----------


async def test_login_single_workspace_returns_token(
    service: AuthService,
    users: AsyncMock,
    members: AsyncMock,
    hasher: MagicMock,
    tokens: MagicMock,
) -> None:
    user = _user()
    membership = make_human(email=user.email)
    users.get_by_email.return_value = user
    members.list_for_user.return_value = [membership]

    response = await service.login(
        LoginRequest(email=user.email, password="hunter2")  # pragma: allowlist secret
    )

    assert response.requires_selection is False
    assert response.access_token == "human.jwt"
    assert response.expires_in == 3600
    hasher.verify.assert_called_once_with("hunter2", "bcrypt$hash")
    tokens.issue_human_token.assert_called_once_with(membership)


async def test_login_multi_workspace_returns_selection(
    service: AuthService,
    users: AsyncMock,
    members: AsyncMock,
    workspaces: AsyncMock,
    tokens: MagicMock,
) -> None:
    user = _user()
    m1 = make_human(email=user.email)
    m2 = make_human(email=user.email)
    users.get_by_email.return_value = user
    members.list_for_user.return_value = [m1, m2]
    ws_a = _workspace("Acme")
    ws_b = _workspace("Beta")
    workspaces.get_by_id.side_effect = lambda wid: (ws_a if wid == m1.workspace_id else ws_b)

    response = await service.login(
        LoginRequest(email=user.email, password="hunter2")  # pragma: allowlist secret
    )

    assert response.requires_selection is True
    assert response.selection_token == "selection.jwt"
    assert response.access_token is None
    assert response.workspaces is not None
    assert {w.workspace_id for w in response.workspaces} == {
        m1.workspace_id,
        m2.workspace_id,
    }
    tokens.issue_human_token.assert_not_called()
    tokens.issue_selection_token.assert_called_once_with(user)


async def test_login_unknown_email(service: AuthService, users: AsyncMock) -> None:
    users.get_by_email.return_value = None
    with pytest.raises(AuthenticationError):
        await service.login(
            LoginRequest(email="ghost@kanea.ai", password="x")  # pragma: allowlist secret
        )


async def test_login_oauth_only_user_rejects_password(
    service: AuthService, users: AsyncMock
) -> None:
    user = _user()
    user.password_hash = None
    users.get_by_email.return_value = user
    with pytest.raises(AuthenticationError):
        await service.login(
            LoginRequest(email=user.email, password="x")  # pragma: allowlist secret
        )


async def test_login_wrong_password(
    service: AuthService, users: AsyncMock, hasher: MagicMock
) -> None:
    users.get_by_email.return_value = _user()
    hasher.verify.return_value = False
    with pytest.raises(AuthenticationError):
        await service.login(
            LoginRequest(email="alice@kanea.ai", password="wrong")  # pragma: allowlist secret
        )


async def test_login_no_memberships(
    service: AuthService, users: AsyncMock, members: AsyncMock
) -> None:
    """A stranded user — auth verifies but they hold no workspace
    memberships. Same response as bad credentials so existence isn't
    leaked."""
    users.get_by_email.return_value = _user()
    members.list_for_user.return_value = []
    with pytest.raises(AuthenticationError):
        await service.login(
            LoginRequest(email="alice@kanea.ai", password="x")  # pragma: allowlist secret
        )


# ---------- select_workspace ----------


async def test_select_workspace_happy_path(
    service: AuthService,
    members: AsyncMock,
    tokens: MagicMock,
) -> None:
    user_id = uuid4()
    membership = make_human()
    tokens.decode_selection_token.return_value = user_id
    members.list_for_user.return_value = [membership]

    response = await service.select_workspace(
        SelectWorkspaceRequest(selection_token="sel.jwt", workspace_id=membership.workspace_id)
    )
    assert response.access_token == "human.jwt"
    tokens.issue_human_token.assert_called_once_with(membership)


async def test_select_workspace_rejects_invalid_token(
    service: AuthService, tokens: MagicMock
) -> None:
    tokens.decode_selection_token.side_effect = jwt.InvalidTokenError("bad")
    with pytest.raises(AuthenticationError):
        await service.select_workspace(
            SelectWorkspaceRequest(selection_token="x", workspace_id=uuid4())
        )


async def test_select_workspace_rejects_non_member(
    service: AuthService, members: AsyncMock, tokens: MagicMock
) -> None:
    """User has memberships but not in the requested workspace —
    they can't elevate via a chosen-but-foreign workspace_id."""
    tokens.decode_selection_token.return_value = uuid4()
    members.list_for_user.return_value = [make_human()]
    with pytest.raises(AuthenticationError):
        await service.select_workspace(
            SelectWorkspaceRequest(selection_token="x", workspace_id=uuid4())
        )


# ---------- agent-token (unchanged) ----------


async def test_agent_token_success(
    service: AuthService,
    members: AsyncMock,
    credentials: AsyncMock,
    hasher: MagicMock,
    tokens: MagicMock,
) -> None:
    agent = make_agent()
    members.get_by_id.return_value = agent
    credentials.get_for_member.return_value = make_credentials(
        member_id=agent.id, agent_secret_hash="bcrypt$agent"
    )

    response = await service.issue_agent_token(
        AgentTokenRequest(agent_id=agent.id, secret="s3cret")
    )

    assert response.access_token == "agent.jwt"
    tokens.issue_agent_token.assert_called_once_with(agent)


async def test_agent_token_unknown_agent(service: AuthService, members: AsyncMock) -> None:
    members.get_by_id.return_value = None
    with pytest.raises(AuthenticationError):
        await service.issue_agent_token(AgentTokenRequest(agent_id=uuid4(), secret="x"))


async def test_agent_token_rejects_human_member(service: AuthService, members: AsyncMock) -> None:
    members.get_by_id.return_value = make_human()
    with pytest.raises(AuthenticationError):
        await service.issue_agent_token(AgentTokenRequest(agent_id=uuid4(), secret="x"))


# ---------- register ----------


async def test_register_creates_user_and_workspace(
    service: AuthService,
    users: AsyncMock,
    workspaces: AsyncMock,
    members: AsyncMock,
    tokens: MagicMock,
) -> None:
    users.get_by_email.return_value = None
    users.create.side_effect = lambda u: u
    workspaces.create.side_effect = lambda ws: ws
    members.create.side_effect = lambda m: m

    response = await service.register(
        RegisterRequest(
            email="alice@kanea.ai",
            password="hunter2hunter2",  # pragma: allowlist secret
            full_name="Alice",
            workspace_name="Acme Corp",
        )
    )

    assert response.access_token == "human.jwt"

    users.create.assert_awaited_once()
    persisted_user = users.create.await_args.args[0]
    assert persisted_user.email == "alice@kanea.ai"
    assert persisted_user.password_hash == "bcrypt$hunter2hunter2"  # pragma: allowlist secret

    members.create.assert_awaited_once()
    persisted_member = members.create.await_args.args[0]
    assert persisted_member.user_id == persisted_user.id
    assert persisted_member.type is MemberType.HUMAN


async def test_register_rejects_duplicate_email(
    service: AuthService, users: AsyncMock, workspaces: AsyncMock, members: AsyncMock
) -> None:
    users.get_by_email.return_value = _user()
    with pytest.raises(EmailAlreadyExistsError):
        await service.register(
            RegisterRequest(
                email="alice@kanea.ai",
                password="hunter2hunter2",  # pragma: allowlist secret
                full_name="Alice",
                workspace_name="Acme",
            )
        )
    users.create.assert_not_called()
    workspaces.create.assert_not_called()
    members.create.assert_not_called()
