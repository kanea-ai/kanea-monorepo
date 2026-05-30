from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.admin.users_ports import (
    AdminMembershipRow,
    AdminUserRepository,
    UserRowWithWorkspaceCount,
)
from app.domain.entities import User
from app.domain.enums import MemberType
from app.infrastructure.db.models import MemberModel, UserModel, WorkspaceModel


def _to_user(row: UserModel) -> User:
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


class SqlAlchemyAdminUserRepository(AdminUserRepository):
    """Cross-tenant user surface served to the back-office."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_users(
        self,
        *,
        name: str | None = None,
        skip: int = 0,
        limit: int = 25,
    ) -> tuple[list[UserRowWithWorkspaceCount], int]:
        # Per-row workspace count via a correlated subquery — same
        # pattern as the admin workspaces listing. Keeps the row count
        # on the users table from multiplying with the joined member
        # rows.
        count_subq = (
            select(func.count(MemberModel.id))
            .where(
                MemberModel.user_id == UserModel.id,
                MemberModel.type == MemberType.HUMAN,
            )
            .correlate(UserModel)
            .scalar_subquery()
            .label("workspace_count")
        )
        base = select(UserModel, count_subq)
        if name is not None and name != "":
            needle = f"%{name.lower()}%"
            base = base.where(
                or_(
                    func.lower(UserModel.email).like(needle),
                    func.lower(UserModel.full_name).like(needle),
                )
            )
        base = base.order_by(UserModel.created_at.desc())

        items_stmt = base.offset(skip).limit(limit)
        items_result = await self._session.execute(items_stmt)
        items: list[UserRowWithWorkspaceCount] = []
        for row in items_result.all():
            user_row: UserModel = row[0]
            items.append(
                UserRowWithWorkspaceCount(
                    user=_to_user(user_row),
                    workspace_count=int(row[1] or 0),
                )
            )

        count_stmt = select(func.count()).select_from(
            select(UserModel.id)
            .where(*(base.whereclause,) if base.whereclause is not None else ())
            .subquery()
        )
        total = (await self._session.execute(count_stmt)).scalar_one()
        return items, int(total)

    async def get_user(self, user_id: UUID) -> User | None:
        row = await self._session.get(UserModel, user_id)
        return _to_user(row) if row is not None else None

    async def list_memberships_for_user(self, user_id: UUID) -> list[AdminMembershipRow]:
        # Single join — members + workspaces — so the back-office
        # detail view comes back in one round-trip.
        stmt = (
            select(
                MemberModel.id,
                MemberModel.role,
                MemberModel.is_suspended,
                WorkspaceModel.id,
                WorkspaceModel.name,
                WorkspaceModel.slug,
            )
            .join(WorkspaceModel, WorkspaceModel.id == MemberModel.workspace_id)
            .where(MemberModel.user_id == user_id)
            .order_by(WorkspaceModel.name)
        )
        result = await self._session.execute(stmt)
        return [
            AdminMembershipRow(
                member_id=row[0],
                role=row[1],
                is_suspended=row[2],
                workspace_id=row[3],
                workspace_name=row[4],
                workspace_slug=row[5],
            )
            for row in result.all()
        ]

    async def set_banned(self, user_id: UUID, *, is_banned: bool) -> User:
        from app.domain.exceptions import InvalidMemberTypeError

        stmt = (
            update(UserModel)
            .where(UserModel.id == user_id)
            .values(is_banned=is_banned)
            .returning(UserModel)
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            raise InvalidMemberTypeError("user not found")
        await self._session.flush()
        return _to_user(row)

    async def force_reset(
        self,
        user_id: UUID,
        *,
        new_password_hash: str,
        sessions_invalidated_at: datetime,
    ) -> User:
        from app.domain.exceptions import InvalidMemberTypeError

        stmt = (
            update(UserModel)
            .where(UserModel.id == user_id)
            .values(
                password_hash=new_password_hash,
                sessions_invalidated_at=sessions_invalidated_at,
            )
            .returning(UserModel)
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            raise InvalidMemberTypeError("user not found")
        await self._session.flush()
        return _to_user(row)
