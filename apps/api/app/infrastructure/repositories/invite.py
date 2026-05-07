from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import Invite
from app.domain.exceptions import InviteNotFoundError
from app.infrastructure.db.models import InviteModel


def _to_entity(row: InviteModel) -> Invite:
    return Invite(
        id=row.id,
        workspace_id=row.workspace_id,
        invited_by_id=row.invited_by_id,
        email=row.email,
        role=row.role,
        token_hash=row.token_hash,
        expires_at=row.expires_at,
        accepted_at=row.accepted_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlAlchemyInviteRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, invite: Invite) -> Invite:
        row = InviteModel(
            id=invite.id,
            workspace_id=invite.workspace_id,
            invited_by_id=invite.invited_by_id,
            email=invite.email,
            role=invite.role,
            token_hash=invite.token_hash,
            expires_at=invite.expires_at,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return _to_entity(row)

    async def get_by_token_hash(self, token_hash: str) -> Invite | None:
        stmt = select(InviteModel).where(InviteModel.token_hash == token_hash)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _to_entity(row) if row is not None else None

    async def mark_accepted(self, invite_id: UUID) -> Invite:
        row = await self._session.get(InviteModel, invite_id)
        if row is None:
            raise InviteNotFoundError("invite not found")
        row.accepted_at = datetime.now(UTC)
        await self._session.flush()
        await self._session.refresh(row)
        return _to_entity(row)
