"""Redis connection management.

Provides async Redis client with connection pooling for use across the application.
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import redis.asyncio as redis
from redis.asyncio import Redis

from core.config import settings

logger = logging.getLogger(__name__)

# Global connection pool - initialized lazily
_pool: redis.ConnectionPool | None = None


def get_connection_pool() -> redis.ConnectionPool:
    """Get or create the Redis connection pool."""
    global _pool
    if _pool is None:
        _pool = redis.ConnectionPool.from_url(
            settings.redis_url,
            max_connections=20,
            decode_responses=True,  # Return strings instead of bytes
            # redis-py 8 defaults to a 5 s socket timeout, the same as our XREAD
            # BLOCK, so idle blocking reads timed out client-side (and a reply could
            # be dropped mid-read). Keep it well above the longest block.
            socket_timeout=30,
        )
        logger.info(f"Created Redis connection pool for {settings.redis_url}")
    return _pool


async def get_redis_client() -> Redis:
    """Get a Redis client from the connection pool.

    Returns:
        Redis client instance with connection from pool.

    Usage:
        redis = await get_redis_client()
        await redis.set("key", "value")
    """
    pool = get_connection_pool()
    return redis.Redis(connection_pool=pool)


@asynccontextmanager
async def redis_client() -> AsyncGenerator[Redis, None]:
    """Context manager for Redis client.

    Ensures proper cleanup of the connection.

    Usage:
        async with redis_client() as r:
            await r.set("key", "value")
    """
    client = await get_redis_client()
    try:
        yield client
    finally:
        await client.aclose()


async def check_redis_connection() -> bool:
    """Check if Redis is reachable.

    Returns:
        True if Redis responds to PING, False otherwise.
    """
    try:
        client = await get_redis_client()
        await client.ping()
        return True
    except redis.ConnectionError as e:
        logger.error(f"Redis connection failed: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error checking Redis: {e}")
        return False


async def close_redis_pool() -> None:
    """Close the Redis connection pool.

    Should be called during application shutdown.
    """
    global _pool
    if _pool is not None:
        await _pool.disconnect()
        _pool = None
        logger.info("Redis connection pool closed")
