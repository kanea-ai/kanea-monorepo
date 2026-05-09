from __future__ import annotations

from enum import StrEnum


class MemberType(StrEnum):
    HUMAN = "HUMAN"
    AGENT = "AGENT"


class TaskStatus(StrEnum):
    """Lifecycle status. Being blocked is orthogonal — it lives on the
    task as `is_blocked` so a task can stay PENDING/IN_PROGRESS while
    waiting on something external."""

    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    CANCELLED = "CANCELLED"


class OAuthProvider(StrEnum):
    GOOGLE = "GOOGLE"
    GITHUB = "GITHUB"


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
