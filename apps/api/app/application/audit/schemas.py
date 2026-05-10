from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.domain.entities import AuditLog
from app.domain.enums import AuditAction, AuditResourceType


class AuditLogResponse(BaseModel):
    """Audit-log row as the api returns it. ``actor_name`` is denormalised
    on read so the UI doesn't need a second round-trip per row."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    actor_member_id: UUID | None
    actor_name: str | None
    action: AuditAction
    resource_type: AuditResourceType
    resource_id: UUID | None
    # Free-form per AuditAction. The UI inspects `changes` shape based on
    # `action` to render readable summaries.
    changes: dict
    created_at: datetime

    @classmethod
    def from_entity(cls, log: AuditLog, *, actor_name: str | None) -> AuditLogResponse:
        return cls(
            id=log.id,
            workspace_id=log.workspace_id,
            actor_member_id=log.actor_member_id,
            actor_name=actor_name,
            action=log.action,
            resource_type=log.resource_type,
            resource_id=log.resource_id,
            changes=log.changes,
            created_at=log.created_at,
        )
