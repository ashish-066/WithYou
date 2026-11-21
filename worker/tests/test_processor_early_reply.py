"""The reply is published before scoring finishes, exactly once."""

import asyncio
import time

from brain.processor import MessageProcessor
from brain.services.reply_publisher import publish_reply_early
from services.streams import StreamMessage

REPLY = "Great, tell me more."


class FakeGraph:
    """Stands in for the LangGraph: publishes, then 'scores' for a while."""

    def __init__(self, fail_after_publish: bool = False, scoring_seconds: float = 0.5):
        self.fail = fail_after_publish
        self.scoring_seconds = scoring_seconds

    async def ainvoke(self, state, config=None):
        async def node():  # LangGraph runs nodes as tasks: the ContextVar must carry over
            await publish_reply_early(REPLY)
            await publish_reply_early("fallback reply")  # must not be sent
            await asyncio.sleep(self.scoring_seconds)
            if self.fail:
                raise RuntimeError("scoring failed")

        await asyncio.create_task(node())
        return {**state, "response": REPLY}


def message() -> StreamMessage:
    return StreamMessage(
        "1-0", "s", "sess", "candidate_response", "I used Redis", "", {"turn_seq": "3"}
    )


async def run(redis, graph):
    sent: list[tuple[str, float]] = []
    start = time.perf_counter()

    async def publish(text: str) -> None:
        sent.append((text, time.perf_counter() - start))

    result = await MessageProcessor(redis, graph=graph).process(message(), publish=publish)
    return sent, result


async def test_reply_sent_before_scoring_finishes(redis):
    sent, result = await run(redis, FakeGraph(scoring_seconds=0.5))

    assert [text for text, _ in sent] == [REPLY]
    assert sent[0][1] < 0.3
    assert result["success"] and result["published"]


async def test_failure_after_reply_is_reported_as_published(redis):
    sent, result = await run(redis, FakeGraph(fail_after_publish=True))

    assert len(sent) == 1
    assert not result["success"]
    assert result["published"]  # worker must ACK, not retry and speak twice


async def test_without_publisher_nothing_is_marked_published(redis):
    result = await MessageProcessor(redis, graph=FakeGraph(scoring_seconds=0)).process(
        message()
    )

    assert result["success"] and not result["published"]
    assert result["response"] == REPLY
