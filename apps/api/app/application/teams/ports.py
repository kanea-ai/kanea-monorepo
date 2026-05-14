from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from app.domain.entities import Team


@runtime_checkable
class TeamRepository(Protocol):
    async def get_by_id(self, team_id: UUID) -> Team | None: ...
    async def list_for_workspace(
        self,
        workspace_id: UUID,
        *,
        department_id: UUID | None = None,
        skip: int = 0,
        limit: int | None = None,
    ) -> tuple[list[Team], int]:
        """Paginated listing.

        Returns ``(items, total)`` where ``total`` is the unfiltered
        count matching ``department_id`` etc. — the size of the full
        result set before ``skip`` / ``limit`` is applied. ``limit=None``
        means "no upper bound" — used by the few callers (member-team
        picker, profile lookup) that need every team.
        """
        ...

    async def create(self, team: Team) -> Team: ...
    async def update(
        self,
        team_id: UUID,
        *,
        name: str | None = None,
        description: str | None = None,
        department_id: UUID | None = None,
        clear_description: bool = False,
        clear_department: bool = False,
    ) -> Team: ...
    async def delete(self, team_id: UUID) -> None: ...
    async def get_department_head_for_team(self, team_id: UUID) -> UUID | None:
        """Walk the team -> department -> head_id link in a single query.

        Returns the head member's id, or ``None`` if the team has no
        department or the department has no head. Used by the
        leadership predicate in TaskService so a Department Head
        inherits team-leader rights on every team in their department.
        """
        ...

    async def list_team_ids_for_department_head(self, member_id: UUID) -> list[UUID]:
        """Inverse lookup: every team that sits under a department
        whose ``head_id`` == ``member_id``. Used by AuditLogService to
        widen a Priority-3 Admin's reach: a department head oversees
        all teams in their department, not just the one they're on."""
        ...
