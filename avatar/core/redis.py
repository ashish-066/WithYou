"""Async Redis connection management.

Provides connection pooling and utilities for Redis operations.
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from redis.asyncio import ConnectionPool, Redis

from core.config import settings

logger = logging.getLogger(__name__)

# Global connection pool
_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    """Get or create the global Redis connection pool."""
    global _pool
    if _pool is None:
        _pool = ConnectionPool.from_url(
            settings.redis_url,
            max_connections=10,
            decode_responses=True,
        )
        logger.info(f"Created Redis connection pool for {settings.redis_url}")
    return _pool


def get_redis_client() -> Redis:
    """Get a Redis client using the global connection pool."""
    return Redis(connection_pool=get_pool())


@asynccontextmanager
async def redis_client() -> AsyncGenerator[Redis, None]:
    """Context manager for Redis client with automatic cleanup."""
    client = get_redis_client()
    try:
        yield client
    finally:
        await client.aclose()


async def close_redis_pool() -> None:
    """Close the global Redis connection pool."""
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None
        logger.info("Closed Redis connection pool")
