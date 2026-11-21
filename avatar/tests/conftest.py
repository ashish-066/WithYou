"""Shared fixtures for avatar tests.

Tests that need Redis use a separate database (default db 15) that is flushed
before and after each test. They are skipped when Redis is not reachable.
"""

import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from alex_db import dispose_engine
from alex_db.testing import migrate_test_database, reset_test_database
from redis.asyncio import Redis

# Make avatar packages (core, services, api, agents) importable when run from anywhere
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TEST_REDIS_URL = os.getenv("TEST_REDIS_URL", "redis://localhost:6379/15")


@pytest_asyncio.fixture
async def redis():
    if TEST_REDIS_URL.rstrip("/").endswith("/0"):
        pytest.fail("TEST_REDIS_URL must not point at db 0 (it is flushed by tests)")
    client = Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        await client.ping()
    except Exception:
        await client.aclose()
        pytest.skip(f"Redis not reachable at {TEST_REDIS_URL}")
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()


@pytest.fixture(scope="session")
def _migrated_test_database():
    try:
        migrate_test_database()
    except Exception as e:
        pytest.skip(f"Test Postgres not reachable (TEST_DATABASE_URL): {e}")


@pytest_asyncio.fixture
async def db(_migrated_test_database):
    """Empty, migrated test database used by the shared alex_db layer."""
    await reset_test_database()
    yield
    await dispose_engine()


@pytest_asyncio.fixture
async def client(redis, db, monkeypatch):
    """The FastAPI app in-process, on the test Redis db and test Postgres,
    with LiveKit calls replaced by fakes."""
    import httpx

    import core.redis as core_redis
    from core.config import settings
    from services.livekit_service import livekit_service

    # The app's own Redis pool must use the test db, on this test's event loop
    monkeypatch.setattr(settings, "redis_url", TEST_REDIS_URL)
    monkeypatch.setattr(core_redis, "_pool", None)

    async def create_room(name):
        return None

    async def noop(*a, **k):
        return None

    monkeypatch.setattr(livekit_service, "create_room", create_room)
    monkeypatch.setattr(livekit_service, "delete_room", noop)
    monkeypatch.setattr(
        livekit_service, "generate_participant_token", lambda **k: "lk-token"
    )

    import main

    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    if core_redis._pool is not None:
        await core_redis._pool.aclose()
    monkeypatch.setattr(core_redis, "_pool", None)
