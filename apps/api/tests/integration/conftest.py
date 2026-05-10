"""Integration-test infrastructure: a real Postgres engine + schema.

The unit-test default is in-memory SQLite (set in ``tests/conftest``).
That's fine for service-level mocks, but the SQLAlchemy models lean
on Postgres-specific types (PgEnum, JSONB, ``gen_random_uuid()``), so
the SQL repo files can't be exercised against SQLite.

This conftest opts the ``tests/integration`` package into a real
Postgres connection driven by the ``KANEA_TEST_DATABASE_URL`` env
var. CI provides one via the ``postgres`` service in
``pr-checks.yml``; locally you can run

    docker run --rm -d -p 5432:5432 \\
      -e POSTGRES_USER=kanea \\
      -e POSTGRES_PASSWORD=kanea \\
      -e POSTGRES_DB=kanea_test postgres:16-alpine

Then point ``KANEA_TEST_DATABASE_URL`` at the matching DSN
(scheme ``postgresql+asyncpg``, user/password ``kanea``, host
``localhost:5432``, db ``kanea_test``) and run
``poetry run pytest tests/integration``.

When ``KANEA_TEST_DATABASE_URL`` is unset, every test in this
package is skipped — keeping ``pytest`` runnable on a workstation
without a live DB.

Engine + session are *function-scoped* on purpose: pytest-asyncio
default ``auto`` mode creates a fresh event loop per test, and
asyncpg connections bind to the loop they were opened in. Sharing
an engine across tests crashes with "Task got Future attached to a
different loop". The trade-off is a per-test ``create_all`` /
``drop_all`` round-trip; on Postgres 16 that's <1s for our schema,
acceptable for the size of this suite.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

# Importing models registers them on Base.metadata so create_all
# picks them up. Linter would otherwise flag the import as unused.
from app.infrastructure.db import models as _models  # noqa: F401
from app.infrastructure.db.base import Base

_PG_URL = os.environ.get("KANEA_TEST_DATABASE_URL")


# Skip the whole integration package when no Postgres is configured.
# This keeps ``pytest`` green on workstations that haven't started a
# DB; CI sets the env var so all integration tests run there.
collect_ignore_glob = [] if _PG_URL else ["test_*.py"]


@pytest_asyncio.fixture
async def pg_session() -> AsyncIterator[AsyncSession]:
    """Per-test engine + session. Creates the full schema on entry,
    drops it on teardown so tests stay independent. NullPool prevents
    the SQLAlchemy connection pool from caching connections across
    event loops (asyncpg doesn't tolerate that)."""
    if not _PG_URL:  # pragma: no cover - skipped by collect_ignore_glob
        import pytest

        pytest.skip("KANEA_TEST_DATABASE_URL is not set")

    engine = create_async_engine(_PG_URL, echo=False, future=True, poolclass=NullPool)

    # Force-create enum types whose original migrations created them
    # outside Base.metadata (notification_type / project_status /
    # task_relation_type / team_role have ``create_type=False``).
    # ``checkfirst=True`` is the idempotency belt.
    from app.infrastructure.db.models import (
        notification_type_enum,
        project_status_enum,
        task_relation_type_enum,
        team_role_enum,
    )

    async with engine.begin() as conn:
        for enum in (
            team_role_enum,
            task_relation_type_enum,
            project_status_enum,
            notification_type_enum,
        ):
            await conn.run_sync(lambda sync_conn, e=enum: e.create(sync_conn, checkfirst=True))
        await conn.run_sync(Base.metadata.create_all)

    sessionmaker = async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        autoflush=False,
    )
    session = sessionmaker()
    try:
        yield session
    finally:
        await session.rollback()
        await session.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        for enum in (
            notification_type_enum,
            project_status_enum,
            task_relation_type_enum,
            team_role_enum,
        ):
            await conn.run_sync(lambda sync_conn, e=enum: e.drop(sync_conn, checkfirst=True))
    await engine.dispose()
