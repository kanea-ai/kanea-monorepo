from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.application.auth.schemas import AgentTokenRequest, LoginRequest, RegisterRequest
from app.application.auth.service import AuthService
from app.domain.entities import Workspace
from app.domain.enums import MemberType
from app.domain.exceptions import AuthenticationError, EmailAlreadyExistsError
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
    h.verify.return_value = True
    h.hash.side_effect = lambda raw: f"bcrypt${raw}"
    return h


@pytest.fixture
def tokens() -> MagicMock:
    t = MagicMock()
    t.issue_human_token.return_value = ("human.jwt", 3600)
    t.issue_agent_token.return_value = ("agent.jwt", 900)
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


# ---------- login ----------


async def test_login_success(
    service: AuthService,
    members: AsyncMock,
    credentials: AsyncMock,
    hasher: MagicMock,
    tokens: MagicMock,
) -> None:
    human = make_human(email="alice@kanea.ai")
    members.get_by_email.return_value = human
    credentials.get_for_member.return_value = make_credentials(
        member_id=human.id, password_hash="bcrypt$hash"
    )

    response = await service.login(
        LoginRequest(email="alice@kanea.ai", password="hunter2")  # pragma: allowlist secret
    )

    assert response.access_token == "human.jwt"
    assert response.token_type == "bearer"
    assert response.expires_in == 3600
    members.get_by_email.assert_awaited_once_with("alice@kanea.ai")
    credentials.get_for_member.assert_awaited_once_with(human.id)
    hasher.verify.assert_called_once_with("hunter2", "bcrypt$hash")
    tokens.issue_human_token.assert_called_once_with(human)


async def test_login_unknown_email(service: AuthService, members: AsyncMock) -> None:
    members.get_by_email.return_value = None

    with pytest.raises(AuthenticationError):
        await service.login(
            LoginRequest(email="ghost@kanea.ai", password="hunter2")  # pragma: allowlist secret
        )


async def test_login_rejects_agent_member(service: AuthService, members: AsyncMock) -> None:
    members.get_by_email.return_value = make_agent()

    with pytest.raises(AuthenticationError):
        await service.login(
            LoginRequest(email="agent@kanea.ai", password="hunter2")  # pragma: allowlist secret
        )


async def test_login_no_credentials_row(
    service: AuthService, members: AsyncMock, credentials: AsyncMock
) -> None:
    human = make_human()
    members.get_by_email.return_value = human
    credentials.get_for_member.return_value = None

    with pytest.raises(AuthenticationError):
        await service.login(LoginRequest(email=human.email or "x@y.z", password="x"))


async def test_login_credentials_missing_password(
    service: AuthService, members: AsyncMock, credentials: AsyncMock
) -> None:
    human = make_human()
    members.get_by_email.return_value = human
    credentials.get_for_member.return_value = make_credentials(
        member_id=human.id, password_hash=None, agent_secret_hash="something"
    )

    with pytest.raises(AuthenticationError):
        await service.login(LoginRequest(email=human.email or "x@y.z", password="x"))


async def test_login_wrong_password(
    service: AuthService,
    members: AsyncMock,
    credentials: AsyncMock,
    hasher: MagicMock,
) -> None:
    human = make_human()
    members.get_by_email.return_value = human
    credentials.get_for_member.return_value = make_credentials(
        member_id=human.id, password_hash="bcrypt$hash"
    )
    hasher.verify.return_value = False

    with pytest.raises(AuthenticationError):
        await service.login(
            LoginRequest(email=human.email or "x@y.z", password="wrong")  # pragma: allowlist secret
        )


# ---------- agent-token ----------


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
    assert response.expires_in == 900
    members.get_by_id.assert_awaited_once_with(agent.id)
    hasher.verify.assert_called_once_with("s3cret", "bcrypt$agent")
    tokens.issue_agent_token.assert_called_once_with(agent)


async def test_agent_token_unknown_agent(service: AuthService, members: AsyncMock) -> None:
    members.get_by_id.return_value = None

    with pytest.raises(AuthenticationError):
        await service.issue_agent_token(AgentTokenRequest(agent_id=uuid4(), secret="x"))


async def test_agent_token_rejects_human_member(service: AuthService, members: AsyncMock) -> None:
    members.get_by_id.return_value = make_human()

    with pytest.raises(AuthenticationError):
        await service.issue_agent_token(AgentTokenRequest(agent_id=uuid4(), secret="x"))


async def test_agent_token_no_credentials_row(
    service: AuthService, members: AsyncMock, credentials: AsyncMock
) -> None:
    agent = make_agent()
    members.get_by_id.return_value = agent
    credentials.get_for_member.return_value = None

    with pytest.raises(AuthenticationError):
        await service.issue_agent_token(AgentTokenRequest(agent_id=agent.id, secret="x"))


async def test_agent_token_missing_secret_hash(
    service: AuthService, members: AsyncMock, credentials: AsyncMock
) -> None:
    agent = make_agent()
    members.get_by_id.return_value = agent
    credentials.get_for_member.return_value = make_credentials(
        member_id=agent.id, password_hash="something", agent_secret_hash=None
    )

    with pytest.raises(AuthenticationError):
        await service.issue_agent_token(AgentTokenRequest(agent_id=agent.id, secret="x"))


async def test_agent_token_wrong_secret(
    service: AuthService,
    members: AsyncMock,
    credentials: AsyncMock,
    hasher: MagicMock,
) -> None:
    agent = make_agent()
    members.get_by_id.return_value = agent
    credentials.get_for_member.return_value = make_credentials(
        member_id=agent.id, agent_secret_hash="bcrypt$agent"
    )
    hasher.verify.return_value = False

    with pytest.raises(AuthenticationError):
        await service.issue_agent_token(AgentTokenRequest(agent_id=agent.id, secret="bad"))


# ---------- register ----------


async def test_register_success(
    service: AuthService,
    workspaces: AsyncMock,
    members: AsyncMock,
    credentials: AsyncMock,
    hasher: MagicMock,
    tokens: MagicMock,
) -> None:
    members.get_by_email.return_value = None

    # Whatever the service constructs for the workspace/member is what the
    # repo "returns" — emulate the create-then-refresh round-trip.
    workspaces.create.side_effect = lambda ws: ws
    members.create.side_effect = lambda m: m
    credentials.create.side_effect = lambda c: c

    response = await service.register(
        RegisterRequest(
            email="alice@kanea.ai",
            password="hunter2hunter2",  # pragma: allowlist secret
            full_name="Alice",
            workspace_name="Acme Corp",
        )
    )

    assert response.access_token == "human.jwt"
    assert response.token_type == "bearer"

    # Workspace was created and slugified.
    workspaces.create.assert_awaited_once()
    created_ws: Workspace = workspaces.create.await_args.args[0]
    assert created_ws.name == "Acme Corp"
    assert created_ws.slug.startswith("acme-corp-")
    assert len(created_ws.slug) > len("acme-corp-")

    # Member is HUMAN, owner-priority, in the new workspace.
    members.create.assert_awaited_once()
    created_member = members.create.await_args.args[0]
    assert created_member.workspace_id == created_ws.id
    assert created_member.type is MemberType.HUMAN
    assert created_member.priority == 1
    assert created_member.email == "alice@kanea.ai"

    # Credentials carry a hashed password (not the plaintext).
    credentials.create.assert_awaited_once()
    created_creds = credentials.create.await_args.args[0]
    assert created_creds.member_id == created_member.id
    assert created_creds.password_hash == "bcrypt$hunter2hunter2"  # pragma: allowlist secret
    assert created_creds.agent_secret_hash is None

    # Token issued against the new member.
    tokens.issue_human_token.assert_called_once_with(created_member)


async def test_register_rejects_duplicate_email(
    service: AuthService,
    workspaces: AsyncMock,
    members: AsyncMock,
    credentials: AsyncMock,
) -> None:
    members.get_by_email.return_value = make_human(email="alice@kanea.ai")

    with pytest.raises(EmailAlreadyExistsError):
        await service.register(
            RegisterRequest(
                email="alice@kanea.ai",
                password="hunter2hunter2",  # pragma: allowlist secret
                full_name="Alice",
                workspace_name="Acme",
            )
        )

    # Nothing was created.
    workspaces.create.assert_not_called()
    members.create.assert_not_called()
    credentials.create.assert_not_called()
