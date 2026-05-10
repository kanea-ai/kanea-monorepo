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
