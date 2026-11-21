"""Proctoring flags are applied by the worker under the session lock."""

import asyncio
import json

from brain.processor import MessageProcessor
from services.state_manager import ContextManager
from services.streams import StreamMessage

FLAG = {"id": "f1", "flag_type": "tab_switch", "severity": "medium", "confidence": 0.8,
        "description": "switched tab", "timestamp": "2026-01-01T00:00:00+00:00"}
NOTE = {"timestamp": FLAG["timestamp"], "tag": "concern", "content": "Tab switch", "turn_number": 0}


def flag_message(flag=FLAG, note=NOTE, mid="2-0"):
    return StreamMessage(mid, "s", "sess", "proctoring_flags", "", "",
                         {"flags": json.dumps([flag]), "notes": json.dumps([note])})


class NoGraph:
    async def ainvoke(self, state, config=None):
        raise AssertionError("flags must not run the interview graph")


async def test_flags_applied_without_running_the_graph(redis):
    p = MessageProcessor(redis, graph=NoGraph())
    result = await p.process(flag_message())
    await p.process(flag_message(mid="3-0"))  # redelivery of the same flag

    assert result["success"] and result["response"] == ""
    state = await ContextManager(redis).get_context("sess")
    assert [f["id"] for f in state["cheat_flags"]] == ["f1"]
    assert len(state["timestamp_notes"]) == 1
    assert state["integrity_score"] < 1.0


async def test_flag_arriving_during_a_slow_turn_is_not_lost(redis):
    class SlowTurn:
        async def ainvoke(self, state, config=None):
            await asyncio.sleep(0.5)  # LLM calls
            return {**state, "response": "ok", "turn_count": state.get("turn_count", 0) + 1}

    p = MessageProcessor(redis, graph=SlowTurn())
    turn = StreamMessage("1-0", "s", "sess", "candidate_response", "my answer", "", {})

    async def flag_mid_turn():
        await asyncio.sleep(0.1)
        return await p.process(flag_message())

    await asyncio.gather(p.process(turn), flag_mid_turn())

    state = await ContextManager(redis).get_context("sess")
    assert [f["id"] for f in state["cheat_flags"]] == ["f1"]
    assert state["turn_count"] == 1
