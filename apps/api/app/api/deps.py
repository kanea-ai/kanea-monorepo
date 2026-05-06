from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.auth.ports import (
    CredentialsRepository,
    MemberRepository,
    PasswordHasher,
    TokenService,
)
from app.application.auth.service import AuthService
from app.core.config import Settings, settings
from app.infrastructure.db.session import get_session
from app.infrastructure.repositories.credentials import SqlAlchemyCredentialsRepository
from app.infrastructure.repositories.member import SqlAlchemyMemberRepository
from app.infrastructure.security.password import BcryptPasswordHasher
from app.infrastructure.security.tokens import JwtSettings, JwtTokenService


def get_settings() -> Settings:
    return settings


@lru_cache(maxsize=1)
def get_password_hasher() -> PasswordHasher:
    return BcryptPasswordHasher()


def get_token_service(
    config: Annotated[Settings, Depends(get_settings)],
) -> TokenService:
    return JwtTokenService(
        JwtSettings(
            secret=config.jwt_secret,
            algorithm=config.jwt_algorithm,
            human_ttl_seconds=config.jwt_human_ttl_seconds,
            agent_ttl_seconds=config.jwt_agent_ttl_seconds,
            issuer=config.jwt_issuer,
        )
    )


SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_member_repository(session: SessionDep) -> MemberRepository:
    return SqlAlchemyMemberRepository(session)


def get_credentials_repository(session: SessionDep) -> CredentialsRepository:
    return SqlAlchemyCredentialsRepository(session)


def get_auth_service(
    members: Annotated[MemberRepository, Depends(get_member_repository)],
    credentials: Annotated[CredentialsRepository, Depends(get_credentials_repository)],
    hasher: Annotated[PasswordHasher, Depends(get_password_hasher)],
    tokens: Annotated[TokenService, Depends(get_token_service)],
) -> AuthService:
    return AuthService(
        members=members,
        credentials=credentials,
        hasher=hasher,
        tokens=tokens,
    )


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
