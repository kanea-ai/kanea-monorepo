from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.application.auth.schemas import AgentTokenRequest, LoginRequest
from app.application.auth.service import AuthService
from app.domain.exceptions import AuthenticationError
from tests.auth.factories import make_agent, make_credentials, make_human


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
    return h


@pytest.fixture
def tokens() -> MagicMock:
    t = MagicMock()
    t.issue_human_token.return_value = ("human.jwt", 3600)
    t.issue_agent_token.return_value = ("agent.jwt", 900)
    return t


@pytest.fixture
def service(
    members: AsyncMock,
    credentials: AsyncMock,
    hasher: MagicMock,
    tokens: MagicMock,
) -> AuthService:
    return AuthService(
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
