"""Session lock renewal and context persistence."""

import asyncio

from services.state_manager import ContextManager


async def test_lock_renewal_keeps_lock_past_ttl(redis):
    cm = ContextManager(redis)
    cm.lock_ttl_ms = 300
    token = await cm.acquire_lock("s1")

    for _ in range(4):  # 600ms total, double the TTL
        await asyncio.sleep(0.15)
        assert await cm.extend_lock("s1", token)

    assert await redis.get("lock:session:s1") == token
    assert await cm.release_lock("s1", token)


async def test_extend_fails_for_other_token(redis):
    cm = ContextManager(redis)
    await cm.acquire_lock("s1")

    assert not await cm.extend_lock("s1", "not-the-token")


async def test_cleared_fields_are_deleted_except_external(redis):
    cm = ContextManager(redis)
    await redis.hset(
        "context:s2", mapping={"end_reason": "user_ended", "video_url": "https://x"}
    )

    state = await cm.get_context("s2")
    state["end_reason"] = None
    state["video_url"] = None  # stale copy; the avatar API owns this field
    await cm.update_context("s2", state)

    stored = await redis.hgetall("context:s2")
    assert "end_reason" not in stored
    assert stored["video_url"] == "https://x"
