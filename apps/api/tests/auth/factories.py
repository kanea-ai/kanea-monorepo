from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.domain.entities import Credentials, Member
from app.domain.enums import MemberType


def make_human(
    *,
    member_id: UUID | None = None,
    workspace_id: UUID | None = None,
    email: str = "alice@kanea.ai",
    name: str = "Alice",
    priority: int = 5,
) -> Member:
    now = datetime.now(UTC)
    return Member(
        id=member_id or uuid4(),
        workspace_id=workspace_id or uuid4(),
        team_id=None,
        type=MemberType.HUMAN,
        name=name,
        email=email,
        priority=priority,
        created_at=now,
        updated_at=now,
    )


def make_agent(
    *,
    member_id: UUID | None = None,
    workspace_id: UUID | None = None,
    name: str = "researcher-bot",
    priority: int = 1,
) -> Member:
    now = datetime.now(UTC)
    return Member(
        id=member_id or uuid4(),
        workspace_id=workspace_id or uuid4(),
        team_id=None,
        type=MemberType.AGENT,
        name=name,
        email=None,
        priority=priority,
        created_at=now,
        updated_at=now,
    )


def make_credentials(
    *,
    member_id: UUID,
    password_hash: str | None = None,
) -> Credentials:
    """HUMAN-only credentials row. AGENT members never have one — their
    auth secret lives in ``agent_api_keys``."""
    now = datetime.now(UTC)
    return Credentials(
        id=uuid4(),
        member_id=member_id,
        password_hash=password_hash,
        created_at=now,
        updated_at=now,
    )
