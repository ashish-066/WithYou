"""Interview records (Postgres) used by the call and dashboard routes."""

from datetime import UTC, datetime
from typing import Any

from alex_db import Interview, session_scope
from sqlalchemy import update

import core.db  # noqa: F401  (configures the database)


async def get_interview(session_id: str) -> Interview | None:
    async with session_scope() as db:
        return await db.get(Interview, session_id)


async def update_interview(session_id: str, **values: Any) -> None:
    async with session_scope() as db:
        await db.execute(
            update(Interview).where(Interview.session_id == session_id).values(**values)
        )


def now() -> datetime:
    return datetime.now(UTC)
