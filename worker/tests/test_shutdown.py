"""Graceful shutdown and readiness: a stop request lets the current message finish."""

import asyncio

from core import readiness
from services.streams import StreamMessage
from worker import BrainWorker


def message(n: int) -> StreamMessage:
    return StreamMessage(
        message_id=f"{n}-0", stream="interview:requests", session_id="s",
        message_type="user_message", content="hi", timestamp="", raw_data={},
    )


class FakeStreams:
    def __init__(self, messages):
        self.messages = messages

    async def consume_pending(self):
        return
        yield

    async def consume(self):
        for m in self.messages:
            yield m
        await asyncio.Event().wait()  # then block like XREADGROUP


class FakeRegistry:
    async def heartbeat(self):
        pass


async def test_stop_during_a_message_finishes_it_and_takes_no_more(monkeypatch):
    worker = BrainWorker()
    worker.stream_manager = FakeStreams([message(1), message(2)])
    worker.registry = FakeRegistry()
    processed = []
    started = asyncio.Event()

    async def setup():
        return True

    async def shutdown():
        worker.running = False

    async def process_message(m):
        started.set()
        await asyncio.sleep(0.05)
        processed.append(m.message_id)

    monkeypatch.setattr(worker, "setup", setup)
    monkeypatch.setattr(worker, "shutdown", shutdown)
    monkeypatch.setattr(worker, "process_message", process_message)

    task = asyncio.create_task(worker.run())
    await started.wait()
    assert worker.processing
    worker.running = False  # what the first SIGTERM does while a message is in progress

    await asyncio.wait_for(task, 1)
    assert processed == ["1-0"]  # finished, and message 2 left pending for reclaim
    assert not worker.processing


def test_readiness_file_tracks_freshness(tmp_path, monkeypatch):
    monkeypatch.setattr(readiness, "READY_FILE", tmp_path / "ready")
    assert not readiness.is_ready()
    readiness.mark_ready()
    assert readiness.is_ready()
    assert not readiness.is_ready(max_age_seconds=0)
    readiness.mark_not_ready()
    assert not readiness.is_ready()
