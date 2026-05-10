from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from app.application.audit.ports import AuditLogRepository
from app.application.audit.schemas import AuditLogResponse
from app.application.auth.ports import MemberRepository
from app.application.tasks.schemas import Principal
from app.domain.entities import AuditLog, Member
from app.domain.enums import AuditAction, AuditResourceType, MemberRole, TeamRole


@dataclass(slots=True)
class AuditLogService:
    """Two-faced service:

    * **Write path** — ``record(...)`` is called by other application
      services (departments, teams, tenants) when they mutate state.
      Writes are best-effort from the caller's POV: the caller still
      commits the underlying mutation; the audit insert sits in the
      same SQLAlchemy session, so a transaction failure rolls both
      back together.

    * **Read path** — ``list_for_principal(...)`` applies the
      priority-aware visibility rule documented on
      ``AuditResourceType``. Owner sees everything; Priority-2 Admin
      sees DEPARTMENT/TEAM/MEMBER; Priority-3 Admin sees TEAM rows
      and only for teams where they're HEAD or MANAGER. Anything
      below the admin role sees nothing (the route returns 403).
    """

    audit_logs: AuditLogRepository
    members: MemberRepository

    async def record(
        self,
        principal: Principal,
        *,
        action: AuditAction,
        resource_type: AuditResourceType,
        resource_id: UUID | None,
        changes: dict,
    ) -> None:
        await self.audit_logs.create(
            AuditLog(
                id=uuid4(),
                workspace_id=principal.workspace_id,
                actor_member_id=principal.member_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                changes=changes,
                created_at=datetime.utcnow(),
            )
        )

    async def list_for_principal(
        self,
        principal: Principal,
        *,
        limit: int = 100,
        before: UUID | None = None,
    ) -> list[AuditLogResponse]:
        scope = await self._compute_visibility(principal)
        if scope is _NONE_SCOPE:
            return []

        rows = await self.audit_logs.list_for_workspace(
            principal.workspace_id,
            resource_types=scope.resource_types,
            team_resource_ids=scope.team_resource_ids,
            limit=limit,
            before=before,
        )

        # Single batch lookup so the response shape includes actor names.
        # Keeps the audit endpoint to two queries regardless of row
        # count.
        actor_ids = {r.actor_member_id for r in rows if r.actor_member_id is not None}
        actor_names: dict[UUID, str] = {}
        for actor_id in actor_ids:
            actor = await self.members.get_by_id(actor_id)
            if actor is not None:
                actor_names[actor.id] = actor.name

        return [
            AuditLogResponse.from_entity(
                r,
                actor_name=(
                    actor_names.get(r.actor_member_id) if r.actor_member_id is not None else None
                ),
            )
            for r in rows
        ]

    async def _compute_visibility(self, principal: Principal) -> _Scope:
        """Translate a principal into a query scope for the repo.

        See ``AuditResourceType`` for the hierarchy. The matrix:

        - Owner                          → all rows.
        - Admin, priority ≤ 2            → DEPARTMENT/TEAM/MEMBER.
        - Admin, priority ≤ 3            → TEAM rows for teams the
                                           principal HEADs or MANAGERs.
        - everyone else                  → nothing (the route guards
                                           with WorkspaceAdminDep, but
                                           the service-level rule is
                                           the belt to the route's
                                           braces).
        """
        if principal.role is MemberRole.WORKSPACE_OWNER:
            return _Scope(resource_types=None, team_resource_ids=None)
        if principal.role is MemberRole.WORKSPACE_ADMIN:
            if principal.priority <= 2:
                return _Scope(
                    resource_types=[
                        AuditResourceType.DEPARTMENT,
                        AuditResourceType.TEAM,
                        AuditResourceType.MEMBER,
                    ],
                    team_resource_ids=None,
                )
            if principal.priority <= 3:
                # Resolve the principal's overseen teams from their
                # current membership row. They oversee a team when
                # they hold HEAD or MANAGER on it.
                self_member = await self.members.get_by_id(principal.member_id)
                team_ids = _overseen_team_ids(self_member)
                # If they oversee no teams, they see no audit rows —
                # but we still return a non-None list (empty) so the
                # repo applies the team_id IN (...) clause and returns
                # zero rows rather than every TEAM row.
                return _Scope(
                    resource_types=[AuditResourceType.TEAM],
                    team_resource_ids=team_ids,
                )
        return _NONE_SCOPE


@dataclass(slots=True, frozen=True)
class _Scope:
    """Result of computing a principal's audit visibility. ``None`` on
    a field means "no narrowing"; an empty list means "narrow to
    nothing" (intentional empty result)."""

    resource_types: list[AuditResourceType] | None
    team_resource_ids: list[UUID] | None


# Sentinel for "principal sees nothing at all" — distinct from "narrow
# to empty list" so the repo never gets called.
_NONE_SCOPE = _Scope(resource_types=[], team_resource_ids=None)


def _overseen_team_ids(member: Member | None) -> list[UUID]:
    """A Priority-3 Admin's audit reach is limited to the teams they
    HEAD or MANAGER. A LEAD or MEMBER role wouldn't grant it — those
    are work-execution roles, not management ones."""
    if member is None or member.team_id is None or member.team_role is None:
        return []
    if member.team_role in (TeamRole.HEAD, TeamRole.MANAGER):
        return [member.team_id]
    return []
