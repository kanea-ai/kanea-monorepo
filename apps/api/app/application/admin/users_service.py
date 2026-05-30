from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.application.admin.users_ports import AdminUserRepository
from app.application.admin.users_schemas import (
    AdminUserDetail,
    AdminUserMembership,
    AdminUserRow,
    BanUserRequest,
    ForcePasswordResetResponse,
)
from app.application.auth.ports import PasswordHasher
from app.application.pagination import Page
from app.domain.entities import User
from app.domain.exceptions import ForbiddenError, InvalidMemberTypeError

logger = logging.getLogger("kanea.admin.users")


@dataclass(slots=True)
class AdminUserService:
    users: AdminUserRepository
    hasher: PasswordHasher

    async def list_users(
        self,
        *,
        name: str | None = None,
        skip: int = 0,
        limit: int = 25,
    ) -> Page[AdminUserRow]:
        """Paginated cross-tenant user listing. ``name`` is a substring
        match against name OR email (the repo applies it server-side)."""
        rows, total = await self.users.list_users(name=name, skip=skip, limit=limit)
        return Page[AdminUserRow](
            items=[_row_from_pair(r.user, r.workspace_count) for r in rows],
            total=total,
        )

    async def get_user_detail(self, user_id: UUID) -> AdminUserDetail:
        user = await self.users.get_user(user_id)
        if user is None:
            raise InvalidMemberTypeError("user not found")
        memberships = await self.users.list_memberships_for_user(user_id)
        return AdminUserDetail(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            is_superadmin=user.is_superadmin,
            is_banned=user.is_banned,
            sessions_invalidated_at=user.sessions_invalidated_at,
            created_at=user.created_at,
            memberships=[
                AdminUserMembership(
                    workspace_id=m.workspace_id,
                    workspace_name=m.workspace_name,
                    workspace_slug=m.workspace_slug,
                    member_id=m.member_id,
                    role=m.role,
                    is_suspended=m.is_suspended,
                )
                for m in memberships
            ],
        )

    async def set_banned(
        self,
        target_user_id: UUID,
        request: BanUserRequest,
        *,
        principal_user_id: UUID,
    ) -> AdminUserDetail:
        """Flip the platform-wide ban. Guards:

        - A superadmin cannot ban themselves (would lock the back-
          office). Returns 403 instead of bricking the operator.
        - A superadmin cannot ban another superadmin via this surface
          — the only way to remove someone's god-mode is the CLI
          ``make_superadmin --revoke`` (matches the elevation path).
        """
        target = await self.users.get_user(target_user_id)
        if target is None:
            raise InvalidMemberTypeError("user not found")
        if target.id == principal_user_id:
            raise ForbiddenError("you cannot ban yourself")
        if target.is_superadmin:
            raise ForbiddenError(
                "superadmins cannot be banned via the API; "
                "use `scripts.make_superadmin --revoke` first"
            )
        # Idempotent — re-banning is a no-op so the audit row doesn't
        # double-stamp the action.
        if target.is_banned == request.is_banned:
            return await self.get_user_detail(target_user_id)
        await self.users.set_banned(target_user_id, is_banned=request.is_banned)
        logger.info(
            "admin.users.ban_toggled",
            extra={
                "user_id": str(target_user_id),
                "is_banned": request.is_banned,
                "by_user_id": str(principal_user_id),
            },
        )
        return await self.get_user_detail(target_user_id)

    async def force_password_reset(
        self,
        target_user_id: UUID,
        *,
        principal_user_id: UUID,
    ) -> ForcePasswordResetResponse:
        """Randomise the password hash AND stamp
        ``sessions_invalidated_at`` so every outstanding JWT bounces
        with 401 on the next request. The target user can no longer
        log in until they run the recovery flow.

        Self-reset is allowed (a superadmin nuking their own session
        is a legitimate "I think my laptop was compromised" move).
        Banning a superadmin is not — they have to revoke themselves
        via the CLI first.

        No real email is sent in this stage; the simulated payload is
        logged at INFO so the operator can grep ``/tmp/kanea-api.log``
        to confirm the action."""
        target = await self.users.get_user(target_user_id)
        if target is None:
            raise InvalidMemberTypeError("user not found")
        placeholder = secrets.token_urlsafe(32)
        new_hash = self.hasher.hash(placeholder)
        now = datetime.now(UTC)
        await self.users.force_reset(
            target_user_id,
            new_password_hash=new_hash,
            sessions_invalidated_at=now,
        )
        simulated_email = (
            f"To: {target.email}\n"
            f"Subject: [Kanea] Password reset requested by platform admin\n"
            f"Body: Your password has been reset by a Kanea operator on "
            f"{now.isoformat()}. Use the account-recovery flow to choose a new "
            f"password. Outstanding sessions have been invalidated."
        )
        logger.info(
            "admin.users.force_password_reset",
            extra={
                "user_id": str(target_user_id),
                "by_user_id": str(principal_user_id),
                "simulated_email": simulated_email,
            },
        )
        return ForcePasswordResetResponse(
            user_id=target_user_id,
            sessions_invalidated_at=now,
            simulated_email=simulated_email,
        )


def _row_from_pair(user: User, workspace_count: int) -> AdminUserRow:
    return AdminUserRow(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_superadmin=user.is_superadmin,
        is_banned=user.is_banned,
        sessions_invalidated_at=user.sessions_invalidated_at,
        created_at=user.created_at,
        workspace_count=workspace_count,
    )
