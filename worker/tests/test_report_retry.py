"""A failed report is written again: fast-model fallback, automatic retries,
and retries for interviews whose live state is gone."""

import json
from datetime import UTC, datetime, timedelta

from alex_db import Interview, session_scope

from brain.processor import MessageProcessor
from brain.tools.slow import report_generator
from services.inactivity_sweep import sweep_inactive
from services.streams import StreamMessage

NOW = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
REPORT = '{"summary": "Short interview.", "strengths": [], "concerns": [], "recommendation": "maybe"}'


class Client:
    def __init__(self, reply):
        self.reply, self.calls = reply, 0

    async def generate(self, prompt, **kwargs):
        self.calls += 1
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


def pool(monkeypatch, slow, fast):
    class Pool:
        def get_slow_client(self):
            return slow

        def get_fast_client(self):
            return fast

    async def get():
        return Pool()

    monkeypatch.setattr(report_generator, "get_llm_pool", get)


async def test_recap_falls_back_to_the_other_model(monkeypatch):
    slow, fast = Client(REPORT), Client(RuntimeError("quota"))
    pool(monkeypatch, slow, fast)
    out = await report_generator.generate_descriptive_report({"session_id": "s", "messages": []})
    assert out.success and out.data["summary"] == "Short interview." and slow.calls == 1


async def test_recap_without_any_model_is_built_from_the_understanding_map(monkeypatch):
    pool(monkeypatch, Client(RuntimeError("down")), Client(RuntimeError("down")))
    state = {
        "session_id": "s", "messages": [], "language": "te-IN",
        "understanding": {"topic": "photosynthesis", "points": [
            {"id": "p1", "text": "మొక్కలు సూర్యరశ్మితో ఆహారం తయారు చేస్తాయి", "status": "understood", "struggled": True},
            {"id": "p2", "text": "ఆక్సిజన్ విడుదల అవుతుంది", "status": "partial", "struggled": True},
        ]},
    }
    out = await report_generator.generate_descriptive_report(state)
    recap = out.data
    assert out.success and out.source == "fallback" and recap["language"] == "te-IN"
    assert recap["covered"] == ["మొక్కలు సూర్యరశ్మితో ఆహారం తయారు చేస్తాయి"]
    assert len(recap["improved"]) == 1 and "ఆక్సిజన్" in recap["next_time"]
    text = json.dumps(recap, ensure_ascii=False).lower()
    assert not any(w in text for w in ("score", "grade", "%", "fail"))


async def test_retry_writes_the_report_from_postgres_when_live_state_is_gone(db, redis, monkeypatch):
    pool(monkeypatch, Client(REPORT), Client(REPORT))
    async with session_scope() as s:
        s.add(Interview(session_id="s9", status="ended", end_reason="user_ended",
                        transcript={"messages": [{"role": "user", "content": "Hi, I'm Ashish"}]},
                        scores={"turn_count": 1}))
    await MessageProcessor(redis, graph=None).process(StreamMessage("1-0", "s", "s9", "regenerate_report", "", "", {}))
    async with session_scope() as s:
        row = await s.get(Interview, "s9")
    assert row.report["summary"] == "Short interview." and row.report_saved_at is not None


async def test_sweep_retries_failed_reports_a_few_times(redis):
    old = (NOW - timedelta(minutes=5)).isoformat()
    await redis.hset("context:f1", mapping={"interview_ended": "1", "last_updated": old,
                                            "report_status": "failed", "report_attempts": "1"})
    await redis.hset("context:f2", mapping={"interview_ended": "1", "last_updated": old,
                                            "report_status": "failed", "report_attempts": "3"})  # gave up
    await redis.hset("context:ok", mapping={"interview_ended": "1", "last_updated": old,
                                            "report_status": "completed"})
    await sweep_inactive(redis, NOW)
    queued = [(e["session_id"], e["message_type"]) for _, e in await redis.xrange("interview:requests")]
    assert queued == [("f1", "regenerate_report")]
    await redis.delete("sweep:inactive:lock")
    await sweep_inactive(redis, NOW)  # same attempt isn't queued twice
    assert len(await redis.xrange("interview:requests")) == 1
