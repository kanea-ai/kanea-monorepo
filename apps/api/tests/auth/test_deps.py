from __future__ import annotations

from unittest.mock import MagicMock

from app.api.deps import (
    get_auth_service,
    get_credentials_repository,
    get_member_repository,
    get_password_hasher,
    get_settings,
    get_token_service,
)
from app.application.auth.service import AuthService
from app.core.config import Settings
from app.infrastructure.repositories.credentials import SqlAlchemyCredentialsRepository
from app.infrastructure.repositories.member import SqlAlchemyMemberRepository
from app.infrastructure.security.password import BcryptPasswordHasher
from app.infrastructure.security.tokens import JwtTokenService


def test_get_settings_returns_settings_instance() -> None:
    config = get_settings()
    assert isinstance(config, Settings)


def test_get_password_hasher_is_singleton() -> None:
    a = get_password_hasher()
    b = get_password_hasher()
    assert isinstance(a, BcryptPasswordHasher)
    assert a is b


def test_get_token_service_uses_settings() -> None:
    config = get_settings()
    service = get_token_service(config)
    assert isinstance(service, JwtTokenService)


def test_get_member_repository_wraps_session() -> None:
    session = MagicMock()
    repo = get_member_repository(session)
    assert isinstance(repo, SqlAlchemyMemberRepository)


def test_get_credentials_repository_wraps_session() -> None:
    session = MagicMock()
    repo = get_credentials_repository(session)
    assert isinstance(repo, SqlAlchemyCredentialsRepository)


def test_get_auth_service_wires_dependencies() -> None:
    session = MagicMock()
    config = get_settings()
    service = get_auth_service(
        members=get_member_repository(session),
        credentials=get_credentials_repository(session),
        hasher=get_password_hasher(),
        tokens=get_token_service(config),
    )
    assert isinstance(service, AuthService)
