from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import Credentials
from app.infrastructure.db.models import CredentialsModel


def _to_entity(row: CredentialsModel) -> Credentials:
    return Credentials(
        id=row.id,
        member_id=row.member_id,
        password_hash=row.password_hash,
        agent_secret_hash=row.agent_secret_hash,
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
