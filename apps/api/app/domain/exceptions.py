from __future__ import annotations


class DomainError(Exception):
    """Base class for domain-layer errors."""


class AuthenticationError(DomainError):
    """Raised when supplied credentials cannot be verified."""


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
