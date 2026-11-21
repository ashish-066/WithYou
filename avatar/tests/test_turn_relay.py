"""Candidate turns are relayed to the Brain with turn numbers."""

import pytest
from livekit.agents import StopResponse, llm

from agents.entrypoint import TURN_HANDLING, BrainRelayAgent, TurnRelay
from services.streams import AvatarStreamManager

REQUESTS = "test:requests"


async def test_turns_published_with_increasing_seq(redis):
    relay = TurnRelay("A", AvatarStreamManager(redis, request_stream=REQUESTS))

    await relay.send("hello there")
    await relay.send("  ")  # blank turns are ignored
    await relay.send("second part")

    entries = [d for _, d in await redis.xrange(REQUESTS)]
    assert [(d["content"], d["turn_seq"]) for d in entries] == [
        ("hello there", "1"),
        ("second part", "2"),
    ]
    assert relay.turn_seq == 2


async def test_failed_publish_does_not_advance_turn_seq(redis):
    sm = AvatarStreamManager(redis, request_stream=REQUESTS)
    relay = TurnRelay("A", sm)
    await relay.send("first")

    async def down(**kwargs):
        raise RuntimeError("redis down")

    sm.publish_transcription = down
    await relay.send("lost")

    # otherwise the reply to "first" would be dropped as stale
    assert relay.turn_seq == 1


async def test_agent_relays_turn_and_stops_local_reply():
    sent: list[str] = []

    class FakeRelay:
        async def send(self, text):
            sent.append(text)

    agent = BrainRelayAgent(FakeRelay())
    message = llm.ChatMessage(role="user", content=["I built a cache layer"])

    with pytest.raises(StopResponse):
        await agent.on_user_turn_completed(None, message)
    assert sent == ["I built a cache layer"]


def test_interruptions_require_words():
    interruption = TURN_HANDLING["interruption"]

    assert interruption["min_words"] >= 2
    assert interruption["resume_false_interruption"] is True


def test_buddy_cannot_be_cut_off_by_its_own_echo_by_default():
    # Laptop speakers: the buddy's voice came back through the mic, interrupted it
    # and became a "learner" turn, in a loop. Mic audio is discarded while it speaks.
    interruption = TURN_HANDLING["interruption"]
    assert interruption["enabled"] is False
    assert interruption["discard_audio_if_uninterruptible"] is True
