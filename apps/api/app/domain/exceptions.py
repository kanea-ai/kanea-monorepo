from __future__ import annotations


class DomainError(Exception):
    """Base class for domain-layer errors."""


class AuthenticationError(DomainError):
    """Raised when supplied credentials cannot be verified."""


class EmailAlreadyExistsError(DomainError):
    """Raised on signup when the email collides with an existing member."""


class WorkspaceNameConflictError(DomainError):
    """Raised on signup when the requested workspace name collides
    with an existing one. Phase 1 enforces global uniqueness on
    workspaces.name."""


class WorkspaceNotFoundError(DomainError):
    """Raised when a workspace id doesn't resolve, or when the path
    workspace_id doesn't match the principal's JWT — returned as 404
    in both cases so existence of OTHER workspaces isn't leaked."""


class InvalidMemberTypeError(DomainError):
    """Raised when an operation receives a member of the wrong type."""


class TaskNotFoundError(DomainError):
    """Raised when a task cannot be located in the requester's workspace."""


class DelegationForbiddenError(DomainError):
    """Raised when delegation violates the workspace's hierarchy rules.

    Priority is encoded numerically with lower numbers meaning higher rank
    (CEO = 1, Agent = 5). A requester may only delegate to members whose
    numerical priority is strictly greater than their own.
    """


class InvalidStatusTransitionError(DomainError):
    """Raised when a status update is not allowed by the workflow rules."""


class ForbiddenError(DomainError):
    """Raised when the requester lacks the role required for the action."""


class InviteNotFoundError(DomainError):
    """Raised when an invite token doesn't match any record."""


class InviteExpiredError(DomainError):
    """Raised when the invite has passed its TTL."""


class InviteAlreadyAcceptedError(DomainError):
    """Raised when the invite has already been accepted; tokens are single-use."""


class AgentNotFoundError(DomainError):
    """Raised when an agent ID doesn't resolve to an AGENT-typed member in the
    requester's workspace. Returned as a 404 — same shape as truly-missing so
    cross-tenant probing reveals nothing."""


class AgentHasCreatedTasksError(DomainError):
    """Raised when DELETE /agents/{id} is attempted but the agent created tasks
    that other members still own. Returned as 409 with guidance."""


class AgentApiKeyNotFoundError(DomainError):
    """Raised when ``DELETE /agents/{id}/api-keys/{key_id}`` targets a
    key that doesn't belong to the agent, doesn't exist, or has already
    been revoked-and-deleted. Returned as 404."""


class TaskNotInDoneStateError(DomainError):
    """Raised when rating a task that hasn't transitioned to DONE."""


class TaskAlreadyRatedError(DomainError):
    """Raised when a second rating is attempted on a task. Tokens are
    single-shot — re-rating is a separate UX we haven't designed yet."""


class ProjectNotFoundError(DomainError):
    """Raised when a project id doesn't resolve in the requester's
    workspace. Returned as 404 — same shape as truly-missing so cross-
    tenant probing reveals nothing."""


class ProjectNameConflictError(DomainError):
    """Raised when create/update would violate the per-workspace name
    uniqueness constraint."""


class DepartmentNotFoundError(DomainError):
    """Raised when a department id doesn't resolve in the requester's
    workspace. Returned as 404 — same shape as truly-missing so
    cross-tenant probing reveals nothing."""


class DepartmentNameConflictError(DomainError):
    """Raised when create/update would violate the per-workspace
    department name uniqueness constraint."""


class DepartmentHeadNotInWorkspaceError(DomainError):
    """Raised when ``head_id`` on a department create/update does not
    resolve to a member of the same workspace. Mapped to 422 by the
    route — it's a request-body validation failure, not a missing
    resource."""


class MemberIsDepartmentHeadError(DomainError):
    """Raised when an admin tries to assign a Team to a member who is
    currently the head of some Department.

    The hierarchy rule is "a Department Head sits above teams" — they
    cannot simultaneously hold a Team rank (MANAGER / LEAD / MEMBER)
    and a head role. To put this member on a team, the admin must
    first remove them from the head_id of their department. Mapped to
    409 at the route."""


class MemberAlreadyDepartmentHeadError(DomainError):
    """Raised when ``head_id`` on a department create/update would
    cause a member to head more than one department. A member can be
    the head of at most one Department (one-to-one constraint, also
    enforced by a partial unique index on ``departments.head_id``).
    Mapped to 409 at the route."""


class MemberSuspendedError(DomainError):
    """Raised when a workspace-scoped JWT belongs to a suspended member.
    The auth dependency catches this and maps to 403 Forbidden so the UI
    can show a clear "your access to this workspace was revoked"
    message; the underlying user can still log in to other workspaces."""


class TeamNotFoundError(DomainError):
    """Raised when a team id doesn't resolve in the requester's
    workspace."""


class TeamNameConflictError(DomainError):
    """Raised when create/update would violate the per-workspace team
    name uniqueness constraint."""


class CrossTeamForbiddenError(DomainError):
    """Raised when a non-admin / non-leadership member tries to create
    a task on a team they don't belong to. Pushes them through the
    cross-team request flow instead of letting them dump tasks
    arbitrarily."""


class TaskRequestNotFoundError(DomainError):
    """Raised when a task request id can't be resolved or is cross-tenant."""


class TaskRequestAlreadyResolvedError(DomainError):
    """Raised when fulfill / reject is called on a non-PENDING request.
    Makes the lifecycle a strict state machine — once resolved, the
    record is immutable."""


class TaskRequestForbiddenError(DomainError):
    """Raised when the requester lacks the team-leadership rank needed
    to fulfill / reject a request, or when a non-admin tries to file
    a request against a task they don't own."""


class TaskRelationSelfLinkError(DomainError):
    """Raised when a caller tries to relate a task to itself. Caught at
    the service boundary; the DB-level CHECK is the belt to the service's
    braces."""


class TaskRelationAlreadyExistsError(DomainError):
    """Raised on a duplicate (source, target, type) tuple. Distinct from
    a generic IntegrityError so the route can map to 409 cleanly."""


class TaskRelationNotFoundError(DomainError):
    """Raised when a relation id doesn't resolve, or when its task is
    cross-tenant (404 to avoid leaking existence)."""


class RatingForbiddenError(DomainError):
    """Raised when the rater isn't the task creator. Only the issuing party
    can rate the work — assignees can't self-rate or rate peers."""


class NotificationNotFoundError(DomainError):
    """Raised when a notification id doesn't resolve for the principal,
    or when it's already read (the mark-read endpoint refuses no-op
    second writes to keep the audit trail honest)."""
