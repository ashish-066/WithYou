"""Request stream reliability: reclaim, keepalive, safe consumer removal."""

import asyncio

import pytest

from core.config import settings
from services.streams import StreamManager

STREAM = "test:requests"
GROUP = "test-workers"


def manager(redis, name: str) -> StreamManager:
    return StreamManager(
        redis, request_stream=STREAM, consumer_group=GROUP, consumer_name=name
    )


@pytest.fixture(autouse=True)
def fast_reclaim(monkeypatch):
    monkeypatch.setattr(settings, "reclaim_interval_seconds", 1)
    monkeypatch.setattr(settings, "reclaim_min_idle_ms", 600)


async def collect(sm: StreamManager, seconds: float) -> list[str]:
    seen: list[str] = []

    async def run():
        async for m in sm.consume(block_ms=200):
            seen.append(m.message_id)

    task = asyncio.create_task(run())
    await asyncio.sleep(seconds)
    task.cancel()
    return seen


async def test_unacked_message_is_redelivered(redis):
    sm = manager(redis, "a")
    await sm.create_consumer_group()
    mid = await redis.xadd(STREAM, {"session_id": "s", "content": "hi"})

    seen = await collect(sm, 2.5)

    assert seen.count(mid) >= 2


async def test_touched_in_flight_message_is_not_reclaimed(redis):
    a, b = manager(redis, "a"), manager(redis, "b")
    await a.create_consumer_group()
    mid = await redis.xadd(STREAM, {"session_id": "s", "content": "x"})
    await redis.xreadgroup(GROUP, "a", {STREAM: ">"}, count=1)

    stolen: list[str] = []

    async def run_b():
        async for m in b.consume(block_ms=200):
            stolen.append(m.message_id)

    task = asyncio.create_task(run_b())
    for _ in range(8):  # "processing" for 1.6s, touching every 200ms
        await asyncio.sleep(0.2)
        await a.touch(mid)
    assert stolen == []

    # once a stops touching (e.g. crashed), b takes it over
    await asyncio.sleep(2.5)
    task.cancel()
    assert mid in stolen


async def test_consumer_with_pending_messages_is_kept(redis):
    a = manager(redis, "a")
    await a.create_consumer_group()
    await redis.xadd(STREAM, {"session_id": "s"})
    await redis.xreadgroup(GROUP, "a", {STREAM: ">"}, count=1)

    assert await a.remove_consumer() is False
    consumers = await redis.xinfo_consumers(STREAM, GROUP)
    assert [c["name"] for c in consumers] == ["a"]


async def test_idle_consumer_is_removed(redis):
    c = manager(redis, "c")
    await c.create_consumer_group()
    await redis.xreadgroup(GROUP, "c", {STREAM: "0"})

    assert await c.remove_consumer() is True


async def test_responses_are_trimmed(redis, monkeypatch):
    monkeypatch.setattr(settings, "stream_maxlen", 10)
    sm = StreamManager(redis, response_stream="test:responses")
    for i in range(500):
        await sm.publish_response(session_id="s", content=str(i))

    length = await redis.xlen("test:responses")
    assert length < 500  # approximate trimming keeps it near the cap
    last = await redis.xrevrange("test:responses", count=1)
    assert last[0][1]["content"] == "499"  # newest entries are kept


async def test_message_dead_lettered_after_max_attempts(redis, monkeypatch):
    import worker as worker_module

    monkeypatch.setattr(settings, "dead_letter_stream", "test:dead")
    w = worker_module.BrainWorker()
    w.redis = redis
    w.stream_manager = manager(redis, "a")
    await w.stream_manager.create_consumer_group()
    mid = await redis.xadd(STREAM, {"session_id": "s1", "message_type": "candidate_response", "content": "x"})
    await redis.xreadgroup(GROUP, "a", {STREAM: ">"}, count=1)
    from services.streams import StreamMessage

    msg = StreamMessage(mid, STREAM, "s1", "candidate_response", "x", "", {"session_id": "s1"})
    for _ in range(settings.max_delivery_attempts):
        await w._record_failure(msg, "LLM timeout")

    dead = await redis.xrange("test:dead")
    assert len(dead) == 1
    assert dead[0][1]["original_id"] == mid and dead[0][1]["error"] == "LLM timeout"
    assert (await redis.xpending(STREAM, GROUP))["pending"] == 0  # acked, not retried again
