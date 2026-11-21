"""Startup schema check used by the services."""

import asyncio
import logging

from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text

from alex_db.migrate import alembic_config, upgrade
from alex_db.session import database_url, get_engine

logger = logging.getLogger(__name__)

# Arbitrary constant identifying "alex schema migration" for pg_advisory_lock
_MIGRATION_LOCK = 7_316_204_419


async def current_revision() -> str | None:
    async with get_engine().connect() as conn:
        return await conn.run_sync(
            lambda sync_conn: MigrationContext.configure(sync_conn).get_current_revision()
        )


def head_revision() -> str | None:
    return ScriptDirectory.from_config(alembic_config(database_url())).get_current_head()


async def ensure_schema(auto_upgrade: bool) -> None:
    """Make sure the database schema matches this code.

    auto_upgrade=True (development): apply pending migrations.
    auto_upgrade=False (production): refuse to start if migrations are pending,
    since running them is an explicit deploy step.
    """
    async with get_engine().connect() as conn:
        await conn.execute(text("SELECT 1"))  # fail fast if the database is unreachable

    current, head = await current_revision(), head_revision()
    if current == head:
        return
    if not auto_upgrade:
        raise RuntimeError(
            f"Database schema is at {current or 'empty'}, code expects {head}. "
            "Run migrations first: python -m alex_db.migrate"
        )
    # Several services may start at once (e.g. mprocs): only one migrates
    async with get_engine().connect() as lock_conn:
        await lock_conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": _MIGRATION_LOCK})
        try:
            current = await current_revision()
            if current != head:
                logger.info(f"Applying database migrations ({current or 'empty'} -> {head})")
                # Alembic's env runs its own event loop; keep it off this one
                await asyncio.to_thread(upgrade, database_url())
        finally:
            await lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _MIGRATION_LOCK})
