from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    s = get_settings()
    return create_async_engine(
        s.database_url,
        pool_size=s.db_pool_size,
        max_overflow=s.db_max_overflow,
        pool_pre_ping=True,
        pool_recycle=1800,
        # Statement timeout protects the pool from runaway queries.
        connect_args={"server_settings": {"statement_timeout": "10000",
                                          "application_name": "campus-lost"}},
    )


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False, autoflush=False)


async def session_dependency() -> AsyncIterator[AsyncSession]:
    """One session per request. Services commit explicitly; anything uncommitted rolls back."""
    async with get_sessionmaker()() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
