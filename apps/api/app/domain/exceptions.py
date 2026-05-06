from __future__ import annotations


class DomainError(Exception):
    """Base class for domain-layer errors."""


class AuthenticationError(DomainError):
    """Raised when supplied credentials cannot be verified."""


class InvalidMemberTypeError(DomainError):
    """Raised when an operation receives a member of the wrong type."""
