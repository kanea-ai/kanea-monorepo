from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import User
from app.domain.enums import OAuthProvider
from app.infrastructure.db.models import UserModel


def _to_entity(row: UserModel) -> User:
    return User(
        id=row.id,
        email=row.email,
        full_name=row.full_name,
        password_hash=row.password_hash,
        oauth_provider=row.oauth_provider,
        oauth_id=row.oauth_id,
        is_superadmin=row.is_superadmin,
        is_banned=row.is_banned,
        sessions_invalidated_at=row.sessions_invalidated_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlAlchemyUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: UUID) -> User | None:
        row = await self._session.get(UserModel, user_id)
        return _to_entity(row) if row is not None else None

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(UserModel).where(UserModel.email == email)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _to_entity(row) if row is not None else None

    async def get_by_oauth_identity(self, provider: OAuthProvider, oauth_id: str) -> User | None:
        stmt = select(UserModel).where(
            UserModel.oauth_provider == provider,
            UserModel.oauth_id == oauth_id,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _to_entity(row) if row is not None else None

    async def create(self, user: User) -> User:
        row = UserModel(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            password_hash=user.password_hash,
            oauth_provider=user.oauth_provider,
            oauth_id=user.oauth_id,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return _to_entity(row)

    async def link_oauth_identity(
        self, user_id: UUID, *, provider: OAuthProvider, oauth_id: str
    ) -> User:
        row = await self._session.get(UserModel, user_id)
        if row is None:  # pragma: no cover - DI invariant
            raise ValueError("user not found")
        row.oauth_provider = provider
        row.oauth_id = oauth_id
        await self._session.flush()
        await self._session.refresh(row)
        return _to_entity(row)

    async def update_password(self, user_id: UUID, password_hash: str) -> User:
        row = await self._session.get(UserModel, user_id)
        if row is None:  # pragma: no cover
            raise ValueError("user not found")
        row.password_hash = password_hash
        await self._session.flush()
        await self._session.refresh(row)
        return _to_entity(row)

    async def update_full_name(self, user_id: UUID, full_name: str) -> User:
        row = await self._session.get(UserModel, user_id)
        if row is None:  # pragma: no cover
            raise ValueError("user not found")
        row.full_name = full_name
        await self._session.flush()
        await self._session.refresh(row)
        return _to_entity(row)
