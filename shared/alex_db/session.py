"""Async engine and sessions.

DATABASE_URL, e.g. postgresql+asyncpg://user:password@host:5432/alex
(a plain postgresql:// URL is accepted and switched to the asyncpg driver).

The engine is created lazily and tied to the running event loop; call
dispose_engine() when the loop ends (service shutdown, between tests).
"""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None
_url_override: str | None = None


def normalize_url(url: str) -> str:
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]
    return url


def database_url() -> str:
    url = _url_override or os.getenv("DATABASE_URL", "")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return normalize_url(url)


def configure(url: str | None) -> None:
    """Use this URL instead of $DATABASE_URL (services pass their settings value)."""
    global _url_override
    _url_override = url


def get_engine() -> AsyncEngine:
    global _engine, _sessionmaker
    if _engine is None:
        _engine = create_async_engine(
            database_url(),
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,  # survive database restarts / idle disconnects
        )
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """A session that commits on success and rolls back on error."""
    get_engine()
    assert _sessionmaker is not None
    async with _sessionmaker() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
