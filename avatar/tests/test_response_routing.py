"""Replies reach exactly their own interview, from the right start position."""

import asyncio
import time

from services.streams import AvatarStreamManager

STREAM = "test:responses"


def manager(redis) -> AvatarStreamManager:
    return AvatarStreamManager(redis, response_stream=STREAM)


async def listen(sm, session_id, seconds, **kwargs) -> list[str]:
    got: list[str] = []

    async def run():
        async for m in sm.consume_responses(session_id=session_id, block_ms=200, **kwargs):
            got.append(m.content)

    task = asyncio.create_task(run())
    await asyncio.sleep(seconds)
    task.cancel()
    return got


async def test_concurrent_sessions_each_get_only_their_replies(redis):
    sm = manager(redis)
    await redis.xadd(STREAM, {"session_id": "A", "content": "early-A"})

    async def publish_later():
        await asyncio.sleep(0.3)
        for i in range(5):
            await redis.xadd(STREAM, {"session_id": "A", "content": f"A{i}"})
            await redis.xadd(STREAM, {"session_id": "B", "content": f"B{i}"})

    pub = asyncio.create_task(publish_later())
    got_a, got_b = await asyncio.gather(listen(sm, "A", 1.2), listen(sm, "B", 1.2))
    await pub

    assert got_a == ["early-A"] + [f"A{i}" for i in range(5)]
    assert got_b == [f"B{i}" for i in range(5)]


async def test_starts_at_room_creation(redis):
    sm = manager(redis)
    await redis.xadd(STREAM, {"session_id": "A", "content": "before-room"})
    await asyncio.sleep(0.01)
    room_ms = int(time.time() * 1000)
    await redis.xadd(STREAM, {"session_id": "A", "content": "intro"})

    start = await sm.response_start_id("A", since_ms=room_ms)

    assert await listen(sm, "A", 0.5, start_id=start) == ["intro"]


async def test_restart_resumes_after_last_spoken(redis):
    sm = manager(redis)
    room_ms = int(time.time() * 1000) - 1000
    first = await redis.xadd(STREAM, {"session_id": "A", "content": "intro"})
    await redis.xadd(STREAM, {"session_id": "A", "content": "second"})
    await sm.mark_spoken("A", first)

    start = await sm.response_start_id("A", since_ms=room_ms)

    assert await listen(sm, "A", 0.5, start_id=start) == ["second"]
