from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError

from app.application.projects.ports import ProjectRepository
from app.application.projects.schemas import (
    CreateProjectRequest,
    ProjectResponse,
    UpdateProjectRequest,
)
from app.application.tasks.schemas import Principal
from app.domain.entities import Project
from app.domain.enums import ProjectStatus
from app.domain.exceptions import ProjectNameConflictError, ProjectNotFoundError


@dataclass(slots=True)
class ProjectService:
    projects: ProjectRepository

    async def list_for_workspace(
        self, principal: Principal, *, include_archived: bool = False
    ) -> list[ProjectResponse]:
        rows = await self.projects.list_for_workspace(
            principal.workspace_id, include_archived=include_archived
        )
        return [ProjectResponse.from_entity(r) for r in rows]

    async def get_by_id(self, project_id: UUID, principal: Principal) -> ProjectResponse:
        project = await self._load_workspace_project(project_id, principal)
        return ProjectResponse.from_entity(project)

    async def create(self, request: CreateProjectRequest, principal: Principal) -> ProjectResponse:
        try:
            project = await self.projects.create(
                Project(
                    id=uuid4(),
                    workspace_id=principal.workspace_id,
                    name=request.name,
                    description=request.description,
                    status=ProjectStatus.ACTIVE,
                )
            )
        except IntegrityError as exc:
            raise ProjectNameConflictError(
                "a project with that name already exists in this workspace"
            ) from exc
        return ProjectResponse.from_entity(project)

    async def update(
        self,
        project_id: UUID,
        request: UpdateProjectRequest,
        principal: Principal,
    ) -> ProjectResponse:
        await self._load_workspace_project(project_id, principal)
        clear_description = (
            "description" in request.model_fields_set and request.description is None
        )
        try:
            updated = await self.projects.update(
                project_id,
                name=request.name,
                description=request.description if not clear_description else None,
                status=request.status,
                clear_description=clear_description,
            )
        except IntegrityError as exc:
            raise ProjectNameConflictError(
                "a project with that name already exists in this workspace"
            ) from exc
        return ProjectResponse.from_entity(updated)

    async def delete(self, project_id: UUID, principal: Principal) -> None:
        """Hard delete. Tasks pointing at the project get their
        project_id set to NULL via the FK CASCADE, so they survive
        as un-projected backlog items rather than disappearing."""
        await self._load_workspace_project(project_id, principal)
        await self.projects.delete(project_id)

    async def _load_workspace_project(self, project_id: UUID, principal: Principal) -> Project:
        project = await self.projects.get_by_id(project_id)
        if project is None or project.workspace_id != principal.workspace_id:
            raise ProjectNotFoundError("project not found")
        return project
