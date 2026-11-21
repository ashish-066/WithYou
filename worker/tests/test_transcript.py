"""The full transcript is kept in Redis and saved with the outcome."""

from alex_db import Interview, session_scope

from brain.processor import MessageProcessor
from services.streams import StreamMessage
from services.transcript import append_message, load_transcript, transcript_key


class ReplyGraph:
    """Answers every message; ends the interview on end_call."""

    def __init__(self):
        self.turn = 0

    async def ainvoke(self, state, config=None):
        self.turn += 1
        out = {**state, "turn_count": self.turn, "response": f"reply {self.turn}"}
        if state.get("interview_ended"):
            out.update(response="Thanks, that's all.", descriptive_report={"summary": "ok"})
        return out


_ids = iter(range(1, 10_000))


def msg(session_id, message_type, content=""):
    # Stream ids are unique per message (the transcript uses them to skip redeliveries)
    return StreamMessage(f"{next(_ids)}-0", "s", session_id, message_type, content, "", {})


async def test_append_and_load(redis):
    await append_message(redis, "s1", "user", "hello", 1)
    await append_message(redis, "s1", "assistant", "   ", 1)  # empty: skipped
    await append_message(redis, "s1", "assistant", "hi there", 1)

    messages = await load_transcript(redis, "s1")
    assert [(m["role"], m["content"], m["turn"]) for m in messages] == [
        ("user", "hello", 1),
        ("assistant", "hi there", 1),
    ]
    assert messages[0]["timestamp"]
    assert await redis.ttl(transcript_key("s1")) > 0
    assert await load_transcript(redis, "missing") is None


async def test_processor_records_full_conversation_and_saves_it(db, redis):
    processor = MessageProcessor(redis, graph=ReplyGraph())
    # Setup only: no reply (the voice agent says the greeting itself)
    await processor.process(msg("s2", "system_init"))
    for i in range(12):  # more than the 10 the state keeps
        await processor.process(msg("s2", "candidate_response", f"answer {i}"))
    await processor.process(StreamMessage("1-0", "s", "s2", "end_call", "", "",
                                          {"end_reason": "user_ended"}))

    messages = await load_transcript(redis, "s2")
    assert messages[0] == {**messages[0], "role": "user", "content": "answer 0"}
    assert messages[1] == {**messages[1], "role": "assistant", "content": "reply 1"}
    assert [m["content"] for m in messages if m["role"] == "user"] == [
        f"answer {i}" for i in range(12)
    ]
    assert messages[-1]["content"] == "Thanks, that's all."
    assert len(messages) == 12 * 2 + 1

    async with session_scope() as s:
        row = await s.get(Interview, "s2")
    assert row.transcript["messages"] == messages


async def test_unchanged_reply_not_recorded_twice(redis):
    class SilentGraph:
        async def ainvoke(self, state, config=None):
            return {**state}  # no node answered: response carried over

    await MessageProcessor(redis, graph=ReplyGraph()).process(msg("s3", "candidate_response", "hi"))
    await MessageProcessor(redis, graph=SilentGraph()).process(msg("s3", "slow_task_trigger"))

    assert len(await load_transcript(redis, "s3")) == 2  # the turn and its reply, once


# =============================================================================
# The written report sees the whole interview
# =============================================================================


async def test_retried_message_is_recorded_once(redis):
    msg_a = StreamMessage("7-0", "s", "s4", "candidate_response", "same answer", "", {})
    processor = MessageProcessor(redis, graph=ReplyGraph())
    await processor.process(msg_a)
    await processor.process(msg_a)  # redelivered after a failure

    users = [m for m in await load_transcript(redis, "s4") if m["role"] == "user"]
    assert [m["content"] for m in users] == ["same answer"]


async def test_closing_step_sees_the_final_answer(redis):
    seen = {}

    class ConcludingGraph:
        async def ainvoke(self, state, config=None):
            seen["transcript"] = await load_transcript(redis, state["session_id"])
            return {**state, "response": "Thanks."}

    await MessageProcessor(redis, graph=ConcludingGraph()).process(
        StreamMessage("9-0", "s", "s5", "candidate_response", "my last answer", "", {})
    )
    assert seen["transcript"][-1]["content"] == "my last answer"


async def test_report_prompt_uses_the_full_transcript(redis, monkeypatch):
    from brain.tools.slow import report_generator

    long_answer = "x" * 500  # longer than the old 200-character cut
    for i in range(15):  # more than the 10 messages the state keeps
        await append_message(redis, "s6", "assistant", f"question {i}", i)
        await append_message(redis, "s6", "user", f"answer {i} {long_answer}", i)

    async def client():
        return redis

    monkeypatch.setattr("core.redis.get_redis_client", client)
    state = {"session_id": "s6", "messages": [{"role": "user", "content": "only recent"}]}
    data = report_generator._build_report_prompt_data(state, await report_generator._load_full_transcript(state))
    convo = data["conversation_summary"]
    assert "question 0" in convo and "answer 14" in convo and "only recent" not in convo
    assert long_answer in convo


def test_report_prompt_without_transcript_falls_back_and_long_ones_are_trimmed():
    from brain.tools.slow import report_generator

    state = {"messages": [{"role": "user", "content": "recent"}]}
    assert report_generator._build_report_prompt_data(state)["conversation_summary"] == "Learner: recent"

    huge = [{"role": "user", "content": f"turn {i} " + "y" * 1500} for i in range(100)]
    convo = report_generator._format_conversation(huge)
    assert len(convo) <= report_generator.MAX_CONVERSATION_CHARS + 100
    assert convo.startswith("Learner: turn 0 ") and "turn 99 " in convo
    assert "messages left out for length" in convo
