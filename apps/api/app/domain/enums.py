from __future__ import annotations

from enum import StrEnum


class MemberType(StrEnum):
    HUMAN = "HUMAN"
    AGENT = "AGENT"


class TaskStatus(StrEnum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    CANCELLED = "CANCELLED"
