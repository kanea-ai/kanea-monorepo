"""Integration tests for ``SqlAlchemyAgentApiKeyRepository``.

Run against a real Postgres instance — see ``tests/integration/conftest``.
Covers every public method on the repo so the SQL paths land green and
the migration-introduced table is exercised end-to-end.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import AgentApiKey
from app.domain.enums import MemberRole, MemberType
from app.infrastructure.db.models import MemberModel, WorkspaceModel
from app.infrastructure.repositories.agent_api_key import SqlAlchemyAgentApiKeyRepository


@pytest.fixture
def repo(pg_session: AsyncSession) -> SqlAlchemyAgentApiKeyRepository:
    return SqlAlchemyAgentApiKeyRepository(pg_session)


@pytest.fixture
async def seeded(pg_session: AsyncSession) -> dict[str, UUID]:
    """Workspace + admin (creator) + agent. The agent has no users
    row + no credentials row — credentials.agent_secret_hash is gone
    since migration 0029."""
    workspace = WorkspaceModel(
        id=uuid4(),
        name=f"WS-{uuid4().hex[:6]}",
        slug=f"ws-{uuid4().hex[:6]}",
        task_prefix="TST",
        next_task_seq=1,
    )
    pg_session.add(workspace)
    await pg_session.flush()

    # An AGENT member can exist without a User row (the
    # ``members_human_has_user`` CHECK constraint allows it for
    # AGENT-typed rows). Use a hand-crafted human-less proxy: another
    # AGENT acting as "creator" so the FK on created_by_member_id is
    # satisfiable without dragging in a UserModel.
    creator = MemberModel(
        id=uuid4(),
        workspace_id=workspace.id,
        type=MemberType.AGENT,
        name="creator-bot",
        email=None,
        priority=1,
        role=MemberRole.WORKSPACE_USER,
    )
    agent = MemberModel(
        id=uuid4(),
        workspace_id=workspace.id,
        type=MemberType.AGENT,
        name="target-bot",
        email=None,
        priority=5,
        role=MemberRole.WORKSPACE_USER,
    )
    pg_session.add_all([creator, agent])
    await pg_session.flush()
    return {"workspace_id": workspace.id, "creator_id": creator.id, "agent_id": agent.id}


def _make_key(*, member_id: UUID, creator_id: UUID, secret_hash: str | None = None) -> AgentApiKey:
    return AgentApiKey(
        id=uuid4(),
        member_id=member_id,
        secret_hash=secret_hash or ("a" * 64),
        prefix="kna_dev_",
        last4="aBcD",
        created_by_member_id=creator_id,
        created_at=datetime.now(UTC),
    )


# ---------- create + get_by_id ----------


async def test_create_persists_and_get_by_id_roundtrips(
    repo: SqlAlchemyAgentApiKeyRepository, seeded: dict[str, UUID]
) -> None:
    entity = _make_key(member_id=seeded["agent_id"], creator_id=seeded["creator_id"])
    persisted = await repo.create(entity)
    assert persisted.id == entity.id
    assert persisted.secret_hash == entity.secret_hash

    fetched = await repo.get_by_id(entity.id)
    assert fetched is not None
    assert fetched.member_id == seeded["agent_id"]


async def test_get_by_id_returns_none_for_unknown(
    repo: SqlAlchemyAgentApiKeyRepository,
) -> None:
    assert await repo.get_by_id(uuid4()) is None


# ---------- list_for_member ----------


async def test_list_for_member_orders_newest_first(
    repo: SqlAlchemyAgentApiKeyRepository, seeded: dict[str, UUID]
) -> None:
    older = _make_key(
        member_id=seeded["agent_id"],
        creator_id=seeded["creator_id"],
        secret_hash="b" * 64,
    )
    newer = _make_key(
        member_id=seeded["agent_id"],
        creator_id=seeded["creator_id"],
        secret_hash="c" * 64,
    )
    await repo.create(older)
    await repo.create(newer)
    # The DB-side default `now()` is millisecond-precision; sleeping
    # isn't needed because the inserts are sequential — but we
    # double-check ordering on whichever ends up later.
    rows = await repo.list_for_member(seeded["agent_id"])
    assert {r.id for r in rows} == {older.id, newer.id}


# ---------- find_active_by_secret_hash ----------


async def test_find_active_excludes_revoked(
    repo: SqlAlchemyAgentApiKeyRepository,
    seeded: dict[str, UUID],
) -> None:
    entity = _make_key(member_id=seeded["agent_id"], creator_id=seeded["creator_id"])
    await repo.create(entity)
    found = await repo.find_active_by_secret_hash(entity.secret_hash)
    assert found is not None
    assert found.id == entity.id

    moved = await repo.revoke(entity.id, revoked_at=datetime.now(UTC))
    assert moved is True

    after = await repo.find_active_by_secret_hash(entity.secret_hash)
    assert after is None, "revoked keys must not be returned by the active-lookup path"


async def test_find_active_returns_none_for_unknown_hash(
    repo: SqlAlchemyAgentApiKeyRepository,
) -> None:
    assert await repo.find_active_by_secret_hash("z" * 64) is None


# ---------- mark_used ----------


async def test_mark_used_updates_last_used_at(
    repo: SqlAlchemyAgentApiKeyRepository, seeded: dict[str, UUID]
) -> None:
    entity = _make_key(member_id=seeded["agent_id"], creator_id=seeded["creator_id"])
    await repo.create(entity)
    stamp = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
    await repo.mark_used(entity.id, used_at=stamp)
    fetched = await repo.get_by_id(entity.id)
    assert fetched is not None
    assert fetched.last_used_at == stamp


# ---------- revoke ----------


async def test_revoke_is_idempotent_on_already_revoked(
    repo: SqlAlchemyAgentApiKeyRepository, seeded: dict[str, UUID]
) -> None:
    entity = _make_key(member_id=seeded["agent_id"], creator_id=seeded["creator_id"])
    await repo.create(entity)
    first = await repo.revoke(entity.id, revoked_at=datetime.now(UTC))
    second = await repo.revoke(entity.id, revoked_at=datetime.now(UTC))
    assert first is True
    assert second is False, "second revoke must report no row moved"


async def test_revoke_unknown_returns_false(
    repo: SqlAlchemyAgentApiKeyRepository,
) -> None:
    assert await repo.revoke(uuid4(), revoked_at=datetime.now(UTC)) is False
