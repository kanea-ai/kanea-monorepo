from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from app.domain.entities import Project
from app.domain.enums import ProjectStatus


@runtime_checkable
class ProjectRepository(Protocol):
    async def get_by_id(self, project_id: UUID) -> Project | None: ...
    async def list_for_workspace(
        self, workspace_id: UUID, *, include_archived: bool = False
    ) -> list[Project]: ...
    async def create(self, project: Project) -> Project: ...
    async def update(
        self,
        project_id: UUID,
        *,
        name: str | None = None,
        description: str | None = None,
        status: ProjectStatus | None = None,
        clear_description: bool = False,
    ) -> Project: ...
    async def delete(self, project_id: UUID) -> None: ...
