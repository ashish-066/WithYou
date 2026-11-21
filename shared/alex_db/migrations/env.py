"""Alembic environment (async, asyncpg)."""

import asyncio

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from alex_db.models import Base
from alex_db.session import normalize_url

target_metadata = Base.metadata


def _run(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def _run_online() -> None:
    url = normalize_url(context.config.get_main_option("sqlalchemy.url"))
    engine = create_async_engine(url)
    async with engine.connect() as connection:
        await connection.run_sync(_run)
    await engine.dispose()


def _run_offline() -> None:
    context.configure(
        url=context.config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    _run_offline()
else:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is None:
        asyncio.run(_run_online())
    else:
        # Called from inside an event loop (e.g. tests): run in a fresh thread loop
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(1) as pool:
            pool.submit(asyncio.run, _run_online()).result()
