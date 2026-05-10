from __future__ import annotations

from enum import StrEnum


class MemberType(StrEnum):
    HUMAN = "HUMAN"
    AGENT = "AGENT"


class TaskStatus(StrEnum):
    """Lifecycle status. Being blocked is orthogonal — it lives on the
    task as `is_blocked` so a task can stay PENDING / IN_PROGRESS /
    IN_REVIEW while waiting on something external.

    IN_REVIEW is the column for work that's done from the executor's
    POV but needs verification — QA, secondary-agent check, reviewer
    sign-off. It sits between IN_PROGRESS and DONE."""

    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    IN_REVIEW = "IN_REVIEW"
    DONE = "DONE"
    CANCELLED = "CANCELLED"


class OAuthProvider(StrEnum):
    GOOGLE = "GOOGLE"
    GITHUB = "GITHUB"


class ProjectStatus(StrEnum):
    """Lifecycle of a Project. ACTIVE projects are visible to the UI by
    default; ARCHIVED projects stay queryable but are hidden from
    pickers and list views unless explicitly requested."""

    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class TaskActivityType(StrEnum):
    """Vocabulary of events recorded in the task activity log. Stored
    as a varchar in the DB so adding a new event type is code-only —
    no migration required. The agent-facing history endpoint groups
    these chronologically with comments to reconstruct the full story
    of a task / project.

    Payload shapes (JSONB column):
    - CREATED:          {title}
    - STATUS_CHANGED:   {from, to}
    - ASSIGNED:         {from, to}        (null/uuid)
    - DELEGATED:        {from, to}        (uuid/uuid via /delegate)
    - BLOCKED:          {reason}
    - UNBLOCKED:        {}
    - PROJECT_CHANGED:  {from, to}        (null/uuid)
    - TEAM_CHANGED:     {from, to}        (null/uuid)
    - RATED:            {score, feedback} (issuer-only single-shot)
    """

    CREATED = "CREATED"
    STATUS_CHANGED = "STATUS_CHANGED"
    ASSIGNED = "ASSIGNED"
    DELEGATED = "DELEGATED"
    BLOCKED = "BLOCKED"
    UNBLOCKED = "UNBLOCKED"
    PROJECT_CHANGED = "PROJECT_CHANGED"
    TEAM_CHANGED = "TEAM_CHANGED"
    RATED = "RATED"
    PRIORITY_CHANGED = "PRIORITY_CHANGED"


class TaskRelationType(StrEnum):
    """Directed relations between two tasks. The inverse views
    (blocked_by, mitigated_by, duplicated_by) are not stored — they're
    computed at read time from the same row stored in the source->target
    direction. RELATES_TO is symmetric: the API queries both ends.

    Convention:
    - BLOCKS:     A blocks B  (B is blocked by A)
    - MITIGATES:  A mitigates B (B is mitigated by A)
    - DUPLICATES: A duplicates B (A is the dup, B is the original)
    - RELATES_TO: undirected reference between A and B
    """

    BLOCKS = "BLOCKS"
    MITIGATES = "MITIGATES"
    DUPLICATES = "DUPLICATES"
    RELATES_TO = "RELATES_TO"


class MemberRole(StrEnum):
    """Workspace-level role a member holds — the **system/access**
    side of the RBAC matrix. Distinct from ``TeamRole`` (the
    **work/task** side).

    Phase 1 renamed the values from OWNER/ADMIN/MEMBER → WORKSPACE_*
    so the JWT, audit log, and UI never confuse a workspace owner
    with a team member. Phase 6 then renamed ``WORKSPACE_MEMBER`` to
    ``WORKSPACE_USER`` to make it unambiguous: a USER has *system*
    access to a workspace, but no inherent task-orchestration power
    — that comes from their TeamRole. The class is still called
    MemberRole because it sits on the Member entity.

    Reach is gated by *priority* on top of role: e.g. a Priority-2
    Admin can manage Departments; a Priority-3 Admin only Teams.
    See ``app/api/deps.py:require_admin_priority_le``.
    """

    WORKSPACE_OWNER = "WORKSPACE_OWNER"
    WORKSPACE_ADMIN = "WORKSPACE_ADMIN"
    WORKSPACE_USER = "WORKSPACE_USER"


class AuditAction(StrEnum):
    """Vocabulary of administrative events recorded in ``audit_logs``.

    Stored as varchar so adding new actions doesn't need a migration.
    Distinct from ``TaskActivityType`` — that one's per-task; this
    one's for org/RBAC events on departments, teams, members.
    """

    CREATED = "CREATED"
    UPDATED = "UPDATED"
    DELETED = "DELETED"
    # Member-specific lifecycle events — captured with their own
    # action name (rather than UPDATED) because they're surfaced
    # separately in the audit UI.
    SUSPENDED = "SUSPENDED"
    SUSPENSION_REVOKED = "SUSPENSION_REVOKED"
    ROLE_CHANGED = "ROLE_CHANGED"
    TEAM_ASSIGNED = "TEAM_ASSIGNED"
    TEAM_UNASSIGNED = "TEAM_UNASSIGNED"


class AuditResourceType(StrEnum):
    """The kind of resource an audit_logs row points at. Used both as
    a column value and as the visibility-scope key for the audit-log
    listing endpoint.

    Hierarchy: ``WORKSPACE`` ⊃ ``DEPARTMENT`` ⊃ ``TEAM`` ⊃ ``MEMBER``.
    The audit-log visibility rule walks this hierarchy: an Owner sees
    every row; a Priority-2 Admin sees DEPARTMENT/TEAM/MEMBER; a
    Priority-3 Admin sees TEAM rows only and only for teams they
    oversee (HEAD/MANAGER on those teams).
    """

    WORKSPACE = "WORKSPACE"
    DEPARTMENT = "DEPARTMENT"
    TEAM = "TEAM"
    MEMBER = "MEMBER"


class RequestStatus(StrEnum):
    """Cross-team task request lifecycle.

    PENDING   : created by a member, awaiting their team's leadership.
    FULFILLED : a MANAGER / LEAD on the source team minted the target
                task and linked it back via BLOCKS.
    REJECTED  : leadership declined; reject_reason is the audit trail.
    """

    PENDING = "PENDING"
    FULFILLED = "FULFILLED"
    REJECTED = "REJECTED"


class NotificationType(StrEnum):
    """Why a notification was sent. Phase 4 ships only mention sources;
    the schema's payload column is JSONB so adding new types later
    (assignments, status changes on watched tasks) won't need a
    migration — only a new enum value here."""

    MENTION_TASK = "MENTION_TASK"
    MENTION_COMMENT = "MENTION_COMMENT"


class TeamRole(StrEnum):
    """A member's rank within a Team. Distinct from MemberRole, which
    governs workspace-level permissions; TeamRole is per-team and
    scopes intra-team responsibilities.

    HEAD    : top leader of the team. Orchestrates resources and sets
              high-level goals across the team's projects.
    MANAGER : manages agents/employees within the team. Tracks KPIs,
              can reassign tasks within the team, and can modify agent
              contexts (model / priority / config).
    LEAD    : technical lead — executes work and can delegate to
              lower-priority members on the same team.
    MEMBER  : standard executor (Human or Agent).
    """

    HEAD = "HEAD"
    MANAGER = "MANAGER"
    LEAD = "LEAD"
    MEMBER = "MEMBER"
