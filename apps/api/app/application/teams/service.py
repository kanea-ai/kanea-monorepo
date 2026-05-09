from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError

from app.application.tasks.schemas import Principal
from app.application.teams.ports import TeamRepository
from app.application.teams.schemas import (
    CreateTeamRequest,
    TeamResponse,
    UpdateTeamRequest,
)
from app.domain.entities import Team
from app.domain.exceptions import TeamNameConflictError, TeamNotFoundError


@dataclass(slots=True)
class TeamService:
    teams: TeamRepository

    async def list_for_workspace(self, principal: Principal) -> list[TeamResponse]:
        rows = await self.teams.list_for_workspace(principal.workspace_id)
        return [TeamResponse.from_entity(t) for t in rows]

    async def create(self, request: CreateTeamRequest, principal: Principal) -> TeamResponse:
        try:
            now = datetime.utcnow()
            team = await self.teams.create(
                Team(
                    id=uuid4(),
                    workspace_id=principal.workspace_id,
                    name=request.name,
                    created_at=now,
                    updated_at=now,
                )
            )
        except IntegrityError as exc:
            raise TeamNameConflictError(
                "a team with that name already exists in this workspace"
            ) from exc
        return TeamResponse.from_entity(team)

    async def update(
        self, team_id: UUID, request: UpdateTeamRequest, principal: Principal
    ) -> TeamResponse:
        await self._load_workspace_team(team_id, principal)
        try:
            updated = await self.teams.update(team_id, name=request.name)
        except IntegrityError as exc:
            raise TeamNameConflictError(
                "a team with that name already exists in this workspace"
            ) from exc
        return TeamResponse.from_entity(updated)

    async def delete(self, team_id: UUID, principal: Principal) -> None:
        await self._load_workspace_team(team_id, principal)
        await self.teams.delete(team_id)

    async def _load_workspace_team(self, team_id: UUID, principal: Principal) -> Team:
        team = await self.teams.get_by_id(team_id)
        if team is None or team.workspace_id != principal.workspace_id:
            raise TeamNotFoundError("team not found")
        return team
