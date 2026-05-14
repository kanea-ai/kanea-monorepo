from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.entities import Department, Member
from app.domain.enums import MemberType


class DepartmentHeadResponse(BaseModel):
    """Compact summary of the member designated as Department Head.
    Embedded in DepartmentResponse so the UI can render the head name
    without a follow-up /members/{id} round-trip."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: str | None
    type: MemberType


class CreateDepartmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=20_000)
    # Optional Department Head. Must resolve to a member of the same
    # workspace; the service validates and 422s otherwise.
    head_id: UUID | None = None


class UpdateDepartmentRequest(BaseModel):
    """Partial update — fields not present in the body stay as-is.
    Setting ``description`` (or ``head_id``) to null explicitly clears
    it; omit the field to leave it untouched."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=20_000)
    head_id: UUID | None = None


class DepartmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    name: str
    description: str | None
    head_id: UUID | None
    head: DepartmentHeadResponse | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_entity(cls, dept: Department, *, head: Member | None = None) -> DepartmentResponse:
        return cls(
            id=dept.id,
            workspace_id=dept.workspace_id,
            name=dept.name,
            description=dept.description,
            head_id=dept.head_id,
            head=(
                DepartmentHeadResponse(
                    id=head.id,
                    name=head.name,
                    email=head.email,
                    type=head.type,
                )
                if head is not None
                else None
            ),
            created_at=dept.created_at,
            updated_at=dept.updated_at,
        )
