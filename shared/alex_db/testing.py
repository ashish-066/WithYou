"""Test helpers: a migrated, emptied test database per test."""

import os
from urllib.parse import urlparse

from sqlalchemy import text

from alex_db.migrate import upgrade
from alex_db.models import Base
from alex_db.session import configure, dispose_engine, get_engine, normalize_url

DEFAULT_TEST_DATABASE_URL = "postgresql://alex:alex-dev-password@127.0.0.1:5434/alex_test"


def test_database_url() -> str:
    url = os.getenv("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)
    name = urlparse(url).path.lstrip("/")
    if not name.endswith("_test"):
        # Tests empty every table: never point them at a real database
        raise RuntimeError(f"TEST_DATABASE_URL must name a *_test database, got {name!r}")
    return normalize_url(url)


def migrate_test_database() -> None:
    upgrade(test_database_url())


async def reset_test_database() -> None:
    """Point the shared layer at the test database and empty every table."""
    await dispose_engine()
    configure(test_database_url())
    tables = ", ".join(t.name for t in reversed(Base.metadata.sorted_tables))
    async with get_engine().begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
