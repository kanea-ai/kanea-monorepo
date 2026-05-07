from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import Member
from app.infrastructure.db.models import MemberModel


def _to_entity(row: MemberModel) -> Member:
    return Member(
        id=row.id,
        workspace_id=row.workspace_id,
        team_id=row.team_id,
        type=row.type,
        name=row.name,
        email=row.email,
        priority=row.priority,
        role=row.role,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlAlchemyMemberRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_email(self, email: str) -> Member | None:
        stmt = select(MemberModel).where(MemberModel.email == email)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _to_entity(row) if row is not None else None

    async def get_by_id(self, member_id: UUID) -> Member | None:
        row = await self._session.get(MemberModel, member_id)
        return _to_entity(row) if row is not None else None

    async def create(self, member: Member) -> Member:
        row = MemberModel(
            id=member.id,
            workspace_id=member.workspace_id,
            team_id=member.team_id,
            type=member.type,
            name=member.name,
            email=member.email,
            priority=member.priority,
            role=member.role,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return _to_entity(row)

    async def list_for_workspace(self, workspace_id: UUID) -> list[Member]:
        stmt = (
            select(MemberModel)
            .where(MemberModel.workspace_id == workspace_id)
            .order_by(MemberModel.priority, MemberModel.created_at)
        )
        result = await self._session.execute(stmt)
        return [_to_entity(row) for row in result.scalars().all()]
