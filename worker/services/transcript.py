"""Full interview transcript in Redis.

The interview state keeps only the last few messages for the prompt; the full
conversation is appended here, one JSON entry per message, and copied to
Postgres with the interview outcome.
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any

from redis.asyncio import Redis

from core.config import settings

logger = logging.getLogger(__name__)


def transcript_key(session_id: str) -> str:
    return f"transcript:{session_id}"


async def append_message(
    redis: Redis,
    session_id: str,
    role: str,
    content: str,
    turn: int | None = None,
    source_id: str | None = None,
) -> None:
    """Append one message. Empty content is skipped. Never raises.

    source_id (the stream message id) makes it idempotent: a message that is
    processed again after a failure isn't recorded twice.
    """
    if not content or not content.strip():
        return
    entry: dict[str, Any] = {
        "role": role,
        "content": content,
        "timestamp": datetime.now(UTC).isoformat(),
        "turn": turn,
    }
    key = transcript_key(session_id)
    try:
        if source_id:
            entry["source_id"] = source_id
            # A redelivered message is at most a reply or two behind
            recent = await redis.lrange(key, -5, -1)
            if any(json.loads(item).get("source_id") == source_id for item in recent):
                return
        async with redis.pipeline(transaction=True) as pipe:
            pipe.rpush(key, json.dumps(entry))
            pipe.expire(key, settings.transcript_ttl_seconds)
            await pipe.execute()
    except Exception as e:
        logger.error(f"Failed to append transcript for {session_id}: {e}")


async def load_transcript(redis: Redis, session_id: str) -> list[dict[str, Any]] | None:
    """The full transcript, or None if none is stored (or Redis failed)."""
    try:
        raw = await redis.lrange(transcript_key(session_id), 0, -1)
    except Exception as e:
        logger.error(f"Failed to load transcript for {session_id}: {e}")
        return None
    if not raw:
        return None
    messages = []
    for item in raw:
        try:
            messages.append(json.loads(item))
        except (TypeError, ValueError):
            continue
    return messages
