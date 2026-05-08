from __future__ import annotations


class DomainError(Exception):
    """Base class for domain-layer errors."""


class AuthenticationError(DomainError):
    """Raised when supplied credentials cannot be verified."""


class EmailAlreadyExistsError(DomainError):
    """Raised on signup when the email collides with an existing member."""


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


class TaskNotInDoneStateError(DomainError):
    """Raised when rating a task that hasn't transitioned to DONE."""


class TaskAlreadyRatedError(DomainError):
    """Raised when a second rating is attempted on a task. Tokens are
    single-shot — re-rating is a separate UX we haven't designed yet."""


class RatingForbiddenError(DomainError):
    """Raised when the rater isn't the task creator. Only the issuing party
    can rate the work — assignees can't self-rate or rate peers."""
