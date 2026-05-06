from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    return create_async_engine(
        settings.database_url,
        echo=settings.database_echo,
        pool_pre_ping=True,
    )


@lru_cache(maxsize=1)
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=get_engine(),
        expire_on_commit=False,
        autoflush=False,
    )


async def get_session() -> AsyncIterator[AsyncSession]:
    """Session-per-request with explicit commit/rollback.

    Without an explicit commit() the AsyncSession context manager closes
    the session in a still-open transaction, which Postgres rolls back —
    so writes from `await session.flush()` are silently lost. Endpoints
    that raise propagate the exception after rollback.
    """
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
