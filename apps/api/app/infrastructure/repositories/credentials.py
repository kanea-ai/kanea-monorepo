from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import Credentials
from app.domain.enums import OAuthProvider
from app.infrastructure.db.models import CredentialsModel


def _to_entity(row: CredentialsModel) -> Credentials:
    return Credentials(
        id=row.id,
        member_id=row.member_id,
        password_hash=row.password_hash,
        oauth_provider=row.oauth_provider,
        oauth_id=row.oauth_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlAlchemyCredentialsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_for_member(self, member_id: UUID) -> Credentials | None:
        stmt = select(CredentialsModel).where(CredentialsModel.member_id == member_id)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _to_entity(row) if row is not None else None

    async def get_by_oauth_identity(self, provider: str, oauth_id: str) -> Credentials | None:
        stmt = select(CredentialsModel).where(
            CredentialsModel.oauth_provider == OAuthProvider(provider),
            CredentialsModel.oauth_id == oauth_id,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _to_entity(row) if row is not None else None

    async def create(self, credentials: Credentials) -> Credentials:
        row = CredentialsModel(
            id=credentials.id,
            member_id=credentials.member_id,
            password_hash=credentials.password_hash,
            oauth_provider=credentials.oauth_provider,
            oauth_id=credentials.oauth_id,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return _to_entity(row)

    async def link_oauth_identity(
        self, member_id: UUID, provider: str, oauth_id: str
    ) -> Credentials:
        """Attach an OAuth identity to an existing member. Used when a user
        with an email/password account signs in via OAuth using the same
        email — we link rather than create a new account."""
        stmt = select(CredentialsModel).where(CredentialsModel.member_id == member_id)
        row = (await self._session.execute(stmt)).scalar_one()
        row.oauth_provider = OAuthProvider(provider)
        row.oauth_id = oauth_id
        await self._session.flush()
        await self._session.refresh(row)
        return _to_entity(row)
