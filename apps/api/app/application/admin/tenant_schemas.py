from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import MemberRole, MemberType, TeamRole


class WorkspaceStatusBreakdown(BaseModel):
    """Counts of tasks in each lifecycle status. Surfaced on the
    workspace detail page as a small "PENDING / IN_PROGRESS /
    IN_REVIEW / DONE / CANCELLED" strip. Missing statuses are
    returned as 0 so the UI doesn't have to coalesce nulls."""

    model_config = ConfigDict(from_attributes=True)

    pending: int
    in_progress: int
    in_review: int
    done: int
    cancelled: int
    blocked: int  # orthogonal flag — surfaced for back-office triage.


class AdminWorkspaceDetail(BaseModel):
    """Back-office workspace detail. Same identifying fields as the
    listing row plus the deeper stats grid (status breakdown,
    department / team / project counts)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    task_prefix: str
    suspended_at: datetime | None
    created_at: datetime
    updated_at: datetime
    total_users: int
    total_tasks: int
    total_tokens_used: int
    total_teams: int
    total_departments: int
    total_projects: int
    status_breakdown: WorkspaceStatusBreakdown


class AdminWorkspaceUserRow(BaseModel):
    """One row in the back-office workspace-users grid. Surfaces the
    hierarchy slot the user sits in (workspace role + team + team
    role) plus the department they head, if any, so the operator can
    eyeball who's structurally where in one glance."""

    model_config = ConfigDict(from_attributes=True)

    member_id: UUID
    # Agents have no backing user row (CHECK constraint on members:
    # HUMAN ⇒ user_id NOT NULL, AGENT ⇒ user_id NULL), so any workspace
    # with even one agent broke serialisation here and 500'd the whole
    # listing. Treat user_id as optional and let the UI handle the
    # agent case explicitly (e.g. hide the Edit affordance).
    user_id: UUID | None
    email: str | None
    full_name: str
    type: MemberType
    role: MemberRole
    is_suspended: bool
    team_id: UUID | None
    team_name: str | None
    team_role: TeamRole | None
    # The dept the user's TEAM belongs to (read-only / derived).
    team_department_id: UUID | None
    team_department_name: str | None
    # The dept the user is the HEAD of, if any. Mutually exclusive
    # with team_id by the Round-2 isolation rule.
    headed_department_id: UUID | None
    headed_department_name: str | None


class PatchWorkspaceUserRequest(BaseModel):
    """Superadmin intervention payload. ``team_id`` / ``team_role``
    drive the team assignment; ``department_id`` drives the head
    appointment.

    Send any subset; omitting a field leaves that side untouched.
    Sending both ``team_id`` (non-null) AND ``department_id`` (non-
    null) is rejected with 400 — a user cannot simultaneously be a
    Department Head and sit on a Team (Round-2 isolation rule)."""

    model_config = ConfigDict(extra="forbid")

    team_id: UUID | None = None
    team_role: TeamRole | None = None
    department_id: UUID | None = None


class PatchWorkspaceMemberRequest(BaseModel):
    """Member-id-keyed superadmin PATCH. Strict superset of
    ``PatchWorkspaceUserRequest``:

    - works for both HUMAN and AGENT members (the user-id-keyed
      endpoint structurally excludes agents because agents have no
      backing user row),
    - adds ``workspace_role`` and ``priority`` so the directory's
      rank + role can be tuned from the back-office in the same
      transaction.

    Send any subset; omitting a field leaves that side untouched.
    The Round-2 dual-scope rule (no member is simultaneously a
    Department Head AND on a Team) is enforced verbatim."""

    model_config = ConfigDict(extra="forbid")

    team_id: UUID | None = None
    team_role: TeamRole | None = None
    department_id: UUID | None = None
    workspace_role: MemberRole | None = None
    priority: int | None = Field(default=None, ge=1, le=100)


class AdminAgentRow(BaseModel):
    """One row in the cross-tenant agent grid. Agents have no global
    user identity (they're members of exactly one workspace), so the
    listing carries workspace context inline. Powers the unified
    /users page in the back-office, where humans + agents are merged
    behind a Type column."""

    model_config = ConfigDict(from_attributes=True)

    member_id: UUID
    workspace_id: UUID
    workspace_name: str
    workspace_slug: str
    full_name: str
    created_at: datetime


class AdminMemberStats(BaseModel):
    """Per-member task stats for the back-office detail panel.
    Same shape regardless of member type — agents and humans both
    have assignments / completions / rated tasks / token usage."""

    model_config = ConfigDict(from_attributes=True)

    assigned_count: int
    completed_count: int
    avg_resolution_seconds: float | None
    accuracy_percent: float | None
    last_activity_at: datetime | None
    total_tokens_used: int
