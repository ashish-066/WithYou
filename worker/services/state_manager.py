"""Context Manager for interview state with distributed locking.

Implements the Redlock algorithm for distributed locking to prevent
race conditions when multiple brain workers process the same session.

Updated for dual-brain architecture with extended state structure.
"""

import json
import logging
import secrets
from datetime import datetime, timezone
from typing import Any

from redis.asyncio import Redis

from brain.state import InterviewState, create_default_interview_state
from core.config import settings

logger = logging.getLogger(__name__)

# Context hash fields set by the avatar service (e.g. video_url on call end).
# A worker's copy of these may be stale None, so never delete them on save.
EXTERNALLY_WRITTEN_FIELDS = {"video_url"}


class LockAcquisitionError(Exception):
    """Raised when a lock cannot be acquired."""

    pass


class LockNotHeldError(Exception):
    """Raised when trying to release a lock that is not held."""

    pass


class ContextManager:
    """Manages interview context in Redis with distributed locking.

    Provides atomic context read/write operations with Redlock-style
    distributed locking to prevent concurrent modifications.

    Usage:
        ctx_mgr = ContextManager(redis_client)

        # Acquire lock before modifying context
        lock_token = await ctx_mgr.acquire_lock(session_id)
        try:
            state = await ctx_mgr.get_context(session_id)
            # ... modify state ...
            await ctx_mgr.update_context(session_id, state)
        finally:
            await ctx_mgr.release_lock(session_id, lock_token)
    """

    def __init__(self, redis: Redis):
        self.redis = redis
        self.lock_ttl_ms = settings.lock_ttl_ms
        self.lock_retry_delay_ms = settings.lock_retry_delay_ms
        self.lock_max_retries = settings.lock_max_retries

    def _lock_key(self, session_id: str) -> str:
        return settings.lock_key.format(session_id=session_id)

    def _context_key(self, session_id: str) -> str:
        return settings.context_key.format(session_id=session_id)

    async def acquire_lock(
        self,
        session_id: str,
        ttl_ms: int | None = None,
        blocking: bool = True,
    ) -> str | None:
        """Acquire a distributed lock for the given session.

        Uses a token-based lock (similar to Redlock) where the lock
        can only be released by the holder of the original token.
        """
        lock_key = self._lock_key(session_id)
        ttl = ttl_ms or self.lock_ttl_ms
        lock_token = secrets.token_hex(16)

        retries = 0
        while True:
            # SET NX (only if not exists) with expiry
            acquired = await self.redis.set(
                lock_key,
                lock_token,
                nx=True,  # Only set if not exists
                px=ttl,  # Expiry in milliseconds
            )

            if acquired:
                logger.debug(f"Lock acquired for session {session_id}")
                return lock_token

            if not blocking:
                return None

            retries += 1
            if retries >= self.lock_max_retries:
                raise LockAcquisitionError(
                    f"Failed to acquire lock for session {session_id} after {retries} retries"
                )

            # Wait before retrying
            await self._sleep_ms(self.lock_retry_delay_ms)

    async def release_lock(self, session_id: str, lock_token: str) -> bool:
        """Release a distributed lock.

        Only releases the lock if the provided token matches the one
        used to acquire it (prevents releasing another worker's lock).
        """
        lock_key = self._lock_key(session_id)

        # Lua script for atomic compare-and-delete
        # Only delete if the value matches our token
        lua_script = """
        if redis.call("GET", KEYS[1]) == ARGV[1] then
            return redis.call("DEL", KEYS[1])
        else
            return 0
        end
        """

        result = await self.redis.eval(lua_script, 1, lock_key, lock_token)
        released = result == 1

        if released:
            logger.debug(f"Lock released for session {session_id}")
        else:
            logger.warning(
                f"Failed to release lock for session {session_id}: token mismatch or lock expired"
            )

        return released

    async def extend_lock(self, session_id: str, lock_token: str, ttl_ms: int | None = None) -> bool:
        """Reset the lock's TTL, only if we still hold it.

        Graph runs make several LLM calls and can outlast the lock TTL, so the
        holder renews it periodically instead of letting it expire mid-run.
        """
        lock_key = self._lock_key(session_id)
        lua_script = """
        if redis.call("GET", KEYS[1]) == ARGV[1] then
            return redis.call("PEXPIRE", KEYS[1], ARGV[2])
        else
            return 0
        end
        """
        result = await self.redis.eval(
            lua_script, 1, lock_key, lock_token, ttl_ms or self.lock_ttl_ms
        )
        return result == 1

    async def get_context(self, session_id: str) -> InterviewState:
        """Fetch the interview context from Redis."""
        context_key = self._context_key(session_id)

        data = await self.redis.hgetall(context_key)

        if not data:
            return create_default_interview_state(session_id)

        return self._deserialize_context(data, session_id)

    async def update_context(self, session_id: str, state: InterviewState) -> None:
        """Update the interview context in Redis."""
        context_key = self._context_key(session_id)

        state["last_updated"] = datetime.now(timezone.utc).isoformat()

        serialized = self._serialize_context(state)

        # HSET only adds/overwrites, so fields cleared to None would keep their
        # old value in Redis. Delete them, except fields other services write.
        cleared = [
            key
            for key, value in state.items()
            if value is None and key not in EXTERNALLY_WRITTEN_FIELDS
        ]

        pipe = self.redis.pipeline(transaction=True)
        if serialized:
            pipe.hset(context_key, mapping=serialized)  # type: ignore
        if cleared:
            pipe.hdel(context_key, *cleared)
        await pipe.execute()
        logger.debug(f"Context updated for session {session_id}")

    async def delete_context(self, session_id: str) -> bool:
        """Delete the interview context from Redis."""
        context_key = self._context_key(session_id)
        result = await self.redis.delete(context_key)
        return result > 0

    async def context_exists(self, session_id: str) -> bool:
        """Check if context exists for a session."""
        context_key = self._context_key(session_id)
        return await self.redis.exists(context_key) > 0

    def _serialize_context(self, state: InterviewState) -> dict[str, str]:
        """Serialize InterviewState to Redis hash-compatible format."""
        result: dict[str, str] = {}

        for key, value in state.items():
            if isinstance(value, (list, dict)):
                result[key] = json.dumps(value)
            elif isinstance(value, bool):
                result[key] = "1" if value else "0"
            elif isinstance(value, float):
                result[key] = str(value)
            elif value is not None:
                result[key] = str(value)

        return result

    def _deserialize_context(self, data: dict[str, Any], session_id: str) -> InterviewState:
        """Deserialize Redis hash data to InterviewState."""
        state = create_default_interview_state(session_id)

        # Fields that need JSON parsing
        json_fields = {
            "messages",
            "message_summary",
            "topics_covered",
            "running_scores",
            "tool_results",
            "tool_queue",
            "tool_results_cache",
            "pending_slow_tasks",
            "completed_slow_tasks",
            "pending_claims",
            "verified_claims",
            "candidate_profile",
            "timestamp_notes",
            "descriptive_report",
            "analytics_data",
            "dfa",
            "skill_tree",
            "flow",
            "candidate_urls",
        }
        int_fields = {"turn_count", "max_turns", "report_attempts"}
        float_fields = {"trust_score"}
        bool_fields = {"interview_ended"}

        for key, value in data.items():
            # Handle bytes from Redis
            if isinstance(value, bytes):
                value = value.decode("utf-8")

            if key in json_fields:
                try:
                    state[key] = json.loads(value)  # type: ignore
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse JSON for {key}")
            elif key in int_fields:
                try:
                    state[key] = int(value)  # type: ignore
                except ValueError:
                    logger.warning(f"Failed to parse int for {key}")
            elif key in float_fields:
                try:
                    state[key] = float(value)  # type: ignore
                except ValueError:
                    logger.warning(f"Failed to parse float for {key}")
            elif key in bool_fields:
                state[key] = value in ("1", "true", "True")  # type: ignore
            else:
                state[key] = value  # type: ignore

        return state

    async def _sleep_ms(self, ms: int) -> None:
        """Async sleep for milliseconds."""
        import asyncio

        await asyncio.sleep(ms / 1000)
