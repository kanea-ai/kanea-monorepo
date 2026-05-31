from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import AgentApiKey
from app.infrastructure.db.models import AgentApiKeyModel


def _to_entity(row: AgentApiKeyModel) -> AgentApiKey:
    return AgentApiKey(
        id=row.id,
        member_id=row.member_id,
        secret_hash=row.secret_hash,
        prefix=row.prefix,
        last4=row.last4,
        label=row.label,
        created_by_member_id=row.created_by_member_id,
        created_at=row.created_at,
        last_used_at=row.last_used_at,
        revoked_at=row.revoked_at,
    )


class SqlAlchemyAgentApiKeyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, key: AgentApiKey) -> AgentApiKey:
        row = AgentApiKeyModel(
            id=key.id,
            member_id=key.member_id,
            secret_hash=key.secret_hash,
            prefix=key.prefix,
            last4=key.last4,
            label=key.label,
            created_by_member_id=key.created_by_member_id,
            last_used_at=key.last_used_at,
            revoked_at=key.revoked_at,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return _to_entity(row)

    async def list_for_member(self, member_id: UUID) -> list[AgentApiKey]:
        stmt = (
            select(AgentApiKeyModel)
            .where(AgentApiKeyModel.member_id == member_id)
            .order_by(AgentApiKeyModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return [_to_entity(r) for r in result.scalars().all()]

    async def get_by_id(self, key_id: UUID) -> AgentApiKey | None:
        row = await self._session.get(AgentApiKeyModel, key_id)
        return _to_entity(row) if row is not None else None

    async def find_active_by_secret_hash(self, secret_hash: str) -> AgentApiKey | None:
        stmt = select(AgentApiKeyModel).where(
            AgentApiKeyModel.secret_hash == secret_hash,
            AgentApiKeyModel.revoked_at.is_(None),
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _to_entity(row) if row is not None else None

    async def mark_used(self, key_id: UUID, *, used_at: datetime) -> None:
        await self._session.execute(
            update(AgentApiKeyModel)
            .where(AgentApiKeyModel.id == key_id)
            .values(last_used_at=used_at)
        )

    async def revoke(self, key_id: UUID, *, revoked_at: datetime) -> bool:
        # Conditional UPDATE: only flips rows that are currently active.
        # rowcount==1 means we moved active → revoked; rowcount==0 means
        # the key was already revoked or doesn't exist — both surface
        # the same idempotent ``False`` to the caller.
        result = await self._session.execute(
            update(AgentApiKeyModel)
            .where(
                AgentApiKeyModel.id == key_id,
                AgentApiKeyModel.revoked_at.is_(None),
            )
            .values(revoked_at=revoked_at)
        )
        return (result.rowcount or 0) > 0
