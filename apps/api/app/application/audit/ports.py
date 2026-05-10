from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from app.domain.entities import AuditLog
from app.domain.enums import AuditResourceType


@runtime_checkable
class AuditLogRepository(Protocol):
    async def create(self, log: AuditLog) -> AuditLog: ...

    async def list_for_workspace(
        self,
        workspace_id: UUID,
        *,
        # Visibility scope. ``resource_types`` narrows to a fixed set of
        # resource_type values; passing ``None`` means "no filter".
        # ``team_resource_ids`` narrows TEAM-typed rows to a specific
        # set of team ids — used when the principal can only see audit
        # rows for teams they oversee. When both are set, the SQL is
        # ``resource_type IN types AND (resource_type != 'TEAM' OR
        # resource_id IN team_resource_ids)``.
        resource_types: list[AuditResourceType] | None = None,
        team_resource_ids: list[UUID] | None = None,
        # Pagination — newest first. The ``total`` returned alongside
        # ``items`` is the unfiltered count under the visibility
        # scope, so the UI can render page numbers.
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[AuditLog], int]: ...
