from __future__ import annotations

from enum import StrEnum


class MemberType(StrEnum):
    HUMAN = "HUMAN"
    AGENT = "AGENT"


class TaskStatus(StrEnum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    BLOCKED = "BLOCKED"
    DONE = "DONE"
    CANCELLED = "CANCELLED"


class OAuthProvider(StrEnum):
    GOOGLE = "GOOGLE"
    GITHUB = "GITHUB"


class MemberRole(StrEnum):
    """Role a member holds within their workspace.

    OWNER  : full control; signed up first or invited as owner. Cannot be
             removed without ownership transfer (rule enforced at the
             service layer, not here).
    ADMIN  : everything except destroying the workspace and managing the
             OWNER. Can invite + manage other ADMINs and MEMBERs.
    MEMBER : default for invited collaborators. Can interact with tasks
             but not the team or billing.
    """

    OWNER = "OWNER"
    ADMIN = "ADMIN"
    MEMBER = "MEMBER"
