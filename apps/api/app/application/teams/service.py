from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError

from app.application.audit.service import AuditLogService
from app.application.departments.ports import DepartmentRepository
from app.application.tasks.schemas import Principal
from app.application.teams.ports import TeamRepository
from app.application.teams.schemas import (
    CreateTeamRequest,
    TeamResponse,
    UpdateTeamRequest,
)
from app.domain.entities import Team
from app.domain.enums import AuditAction, AuditResourceType
from app.domain.exceptions import (
    DepartmentNotFoundError,
    TeamNameConflictError,
    TeamNotFoundError,
)


@dataclass(slots=True)
class TeamService:
    teams: TeamRepository
    # Optional so legacy unit-test constructors stay valid; the
    # create / update paths raise if a department_id is supplied
    # without the lookup wired.
    departments: DepartmentRepository | None = None
    audit_logs: AuditLogService | None = None

    async def list_for_workspace(
        self,
        principal: Principal,
        *,
        department_id: UUID | None = None,
    ) -> list[TeamResponse]:
        rows = await self.teams.list_for_workspace(
            principal.workspace_id, department_id=department_id
        )
        return [TeamResponse.from_entity(t) for t in rows]

    async def create(self, request: CreateTeamRequest, principal: Principal) -> TeamResponse:
        # Cross-tenant guard for the optional department_id. Without
        # this the FK alone accepts another workspace's UUID and the
        # team lands silently filed under a department the principal
        # can't even see.
        if request.department_id is not None:
            await self._verify_department(request.department_id, principal)

        try:
            now = datetime.utcnow()
            team = await self.teams.create(
                Team(
                    id=uuid4(),
                    workspace_id=principal.workspace_id,
                    name=request.name,
                    description=request.description,
                    department_id=request.department_id,
                    created_at=now,
                    updated_at=now,
                )
            )
        except IntegrityError as exc:
            raise TeamNameConflictError(
                "a team with that name already exists in this workspace"
            ) from exc
        if self.audit_logs is not None:
            await self.audit_logs.record(
                principal,
                action=AuditAction.CREATED,
                resource_type=AuditResourceType.TEAM,
                resource_id=team.id,
                changes={
                    "name": team.name,
                    "description": team.description,
                    "department_id": str(team.department_id) if team.department_id else None,
                },
            )
        return TeamResponse.from_entity(team)

    async def update(
        self, team_id: UUID, request: UpdateTeamRequest, principal: Principal
    ) -> TeamResponse:
        before = await self._load_workspace_team(team_id, principal)

        clear_description = (
            "description" in request.model_fields_set and request.description is None
        )
        clear_department = (
            "department_id" in request.model_fields_set and request.department_id is None
        )
        if request.department_id is not None:
            await self._verify_department(request.department_id, principal)

        try:
            updated = await self.teams.update(
                team_id,
                name=request.name,
                description=request.description if not clear_description else None,
                department_id=request.department_id if not clear_department else None,
                clear_description=clear_description,
                clear_department=clear_department,
            )
        except IntegrityError as exc:
            raise TeamNameConflictError(
                "a team with that name already exists in this workspace"
            ) from exc
        if self.audit_logs is not None:
            diff = _field_diff(
                {
                    "name": before.name,
                    "description": before.description,
                    "department_id": (str(before.department_id) if before.department_id else None),
                },
                {
                    "name": updated.name,
                    "description": updated.description,
                    "department_id": (
                        str(updated.department_id) if updated.department_id else None
                    ),
                },
            )
            if diff:
                await self.audit_logs.record(
                    principal,
                    action=AuditAction.UPDATED,
                    resource_type=AuditResourceType.TEAM,
                    resource_id=updated.id,
                    changes=diff,
                )
        return TeamResponse.from_entity(updated)

    async def delete(self, team_id: UUID, principal: Principal) -> None:
        before = await self._load_workspace_team(team_id, principal)
        await self.teams.delete(team_id)
        if self.audit_logs is not None:
            await self.audit_logs.record(
                principal,
                action=AuditAction.DELETED,
                resource_type=AuditResourceType.TEAM,
                resource_id=before.id,
                changes={
                    "name": before.name,
                    "description": before.description,
                    "department_id": (str(before.department_id) if before.department_id else None),
                },
            )

    async def _load_workspace_team(self, team_id: UUID, principal: Principal) -> Team:
        team = await self.teams.get_by_id(team_id)
        if team is None or team.workspace_id != principal.workspace_id:
            raise TeamNotFoundError("team not found")
        return team

    async def _verify_department(self, department_id: UUID, principal: Principal) -> None:
        if self.departments is None:  # pragma: no cover - DI invariant
            raise RuntimeError("department repo not wired")
        dept = await self.departments.get_by_id(department_id)
        if dept is None or dept.workspace_id != principal.workspace_id:
            raise DepartmentNotFoundError("department not found")


def _field_diff(before: dict, after: dict) -> dict:
    """Build the {field: {from, to}} shape we use for UPDATED audit
    rows. Only fields that actually changed are included."""
    diff: dict[str, dict] = {}
    for key in set(before) | set(after):
        if before.get(key) != after.get(key):
            diff[key] = {"from": before.get(key), "to": after.get(key)}
    return diff
