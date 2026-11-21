"""How interviews move towards their end (brain/interview_flow.py) and how the
worker applies it (brain/processor.py, services/inactivity_sweep.py)."""

import json
from datetime import UTC, datetime, timedelta

from brain import interview_flow as flow
from brain.processor import MessageProcessor
from services.inactivity_sweep import sweep_inactive
from services.streams import StreamMessage

NOW = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)


def state(minutes=5.0, **extra):
    return {
        "session_id": "s1",
        "started_at": (NOW - timedelta(minutes=minutes)).isoformat(),
        "turn_count": 4,
        **extra,
    }


SETTLED_TREE = {
    "skill_weights": {"python": 0.5, "sql": 0.45, "trivia": 0.05},
    "evidence_counts": {"python": 4, "sql": 3, "trivia": 0},
    "current_levels": {"python": 3, "sql": 2, "trivia": 0},
}


# =============================================================================
# Rules
# =============================================================================


def test_goodbye_words_inside_an_answer_dont_count():
    assert not flow.wants_to_stop("I built the cache, and that's all I did on that project")
    assert not flow.wants_to_stop("I'd like to finish this function first")
    assert flow.wants_to_stop("I think that's all from me.")
    assert flow.wants_to_stop("I want to stop the interview")


def test_goodbye_asks_for_confirmation_then_ends_on_yes():
    d = flow.before_candidate_turn(state(), "I'd like to stop here", NOW)
    assert d.action == "continue" and "confirm" in d.instruction and d.flow["phase"] == "confirm_end"

    yes = flow.before_candidate_turn(state(flow=d.flow), "Yes, please", NOW)
    assert (yes.action, yes.end_reason) == ("conclude", "candidate_ended")

    no = flow.before_candidate_turn(state(flow=d.flow), "No, let's continue", NOW)
    assert no.action == "continue" and no.flow["phase"] == "interview"
    assert "continue" in no.instruction


def test_wraps_up_on_time_then_closes_after_candidate_questions():
    d = flow.before_candidate_turn(state(minutes=37), "Here's my answer", NOW)
    assert d.instruction == flow.INSTRUCTIONS["wrap_up"] and d.flow["wrap_up_reason"] == "time"

    asking = flow.before_candidate_turn(state(minutes=38, flow=d.flow), "No, but how big is the team?", NOW)
    assert asking.action == "continue" and asking.instruction == flow.INSTRUCTIONS["closing"]

    done = flow.before_candidate_turn(state(minutes=39, flow=d.flow), "No, that's all, thank you", NOW)
    assert (done.action, done.end_reason) == ("conclude", "completed")

    # Closing can't run on forever
    later = NOW + timedelta(minutes=4)
    over = flow.before_candidate_turn(state(minutes=41, flow=d.flow), "One more thing about the team", later)
    assert over.end_reason == "completed"


def test_wraps_up_early_only_when_ratings_are_settled_and_after_the_minimum():
    history = {"python": [3.0, 3.0], "sql": [2.0, 2.0]}
    settled = state(minutes=16, skill_tree=SETTLED_TREE, flow={"level_history": history})
    d = flow.before_candidate_turn(settled, "answer", NOW)
    assert d.flow["wrap_up_reason"] == "assessment_complete"

    too_early = state(minutes=10, skill_tree=SETTLED_TREE, flow={"level_history": history})
    assert flow.before_candidate_turn(too_early, "answer", NOW).instruction == ""

    moving = state(minutes=16, skill_tree=SETTLED_TREE, flow={"level_history": {**history, "sql": [1.0, 2.0]}})
    assert flow.before_candidate_turn(moving, "answer", NOW).instruction == ""


def test_safety_nets():
    assert flow.before_candidate_turn(state(minutes=61), "answer", NOW).end_reason == "time_limit"
    assert flow.before_candidate_turn(state(turn_count=39), "answer", NOW).end_reason == "turn_limit"


def test_unanswered_and_returned_replace_the_question():
    d = flow.on_unanswered(state())
    assert d.instruction == flow.INSTRUCTIONS["move_on"]
    assert (d.flow["unanswered_total"], d.flow["unanswered_in_a_row"]) == (1, 1)
    # An answer resets the run of unanswered questions, not the total
    d2 = flow.before_candidate_turn(state(flow=d.flow), "answer", NOW)
    assert (d2.flow["unanswered_total"], d2.flow["unanswered_in_a_row"]) == (1, 0)

    r = flow.on_returned(state(interview_mode="round2_dsa"))
    assert r.instruction == flow.INSTRUCTIONS["replace_question_coding"] and r.flow["absences"] == 1


def test_long_silence_then_long_answer_is_flagged():
    long_answer = " ".join(["word"] * 80)
    f, flag = flow.record_timing(state(), 24_000, long_answer, 5, NOW)
    assert flag["flag_type"] == "suspicious_timing" and "24 s" in flag["description"]
    assert f["response_timings"] == [{"turn": 5, "latency_ms": 24_000, "words": 80}]
    assert flow.record_timing(state(), 24_000, "short answer", 5, NOW)[1] is None
    assert flow.record_timing(state(), 2_000, long_answer, 5, NOW)[1] is None


def test_completion_summary_is_honest_about_incomplete_interviews():
    s = state(minutes=12, end_reason="no_response", skill_tree=SETTLED_TREE,
              flow={"unanswered_total": 3, "absences": 1})
    c = flow.completion_summary(s, NOW)
    assert c["incomplete"] and c["minutes"] == 12.0
    assert (c["unanswered_questions"], c["absences"], c["skills_not_assessed"]) == (3, 1, ["trivia"])


# =============================================================================
# In the worker
# =============================================================================


class EchoGraph:
    """Records what the graph saw; ends like the real conclude node."""

    def __init__(self):
        self.seen = []

    async def ainvoke(self, st, config=None):
        self.seen.append(dict(st))
        out = {**st, "turn_count": (st.get("turn_count") or 0) + 1, "response": "ok"}
        if st.get("interview_ended"):
            out["response"] = flow.closing_message(st.get("end_reason"))
        return out


def msg(n, message_type, content="", **raw):
    return StreamMessage(f"{n}-0", "s", "s1", message_type, content, "", raw)


async def test_processor_confirms_goodbye_and_signals_the_end(redis):
    graph = EchoGraph()
    p = MessageProcessor(redis, graph=graph)

    r = await p.process(msg(1, "candidate_response", "I want to stop the interview"))
    assert "confirm" in graph.seen[-1]["interviewer_instruction"] and not r["ended_now"]

    r = await p.process(msg(2, "candidate_response", "Yes"))
    assert r["ended_now"] and r["end_reason"] == "candidate_ended"
    assert r["response"] == flow.CLOSING_MESSAGES["candidate_ended"]

    # After the end, candidate-side messages change nothing
    r = await p.process(msg(3, "candidate_response", "hello?"))
    assert r["response"] == "" and len(graph.seen) == 2
    r = await p.process(msg(4, "question_unanswered"))
    assert r["response"] == "" and len(graph.seen) == 2
    # A late End button press doesn't rewrite how it ended or redo the report
    r = await p.process(msg(5, "end_call", end_reason="user_ended"))
    assert len(graph.seen) == 2
    assert (await p.context_manager.get_context("s1"))["end_reason"] == "candidate_ended"


async def test_processor_moves_on_after_no_answer_and_records_timing(redis):
    graph = EchoGraph()
    p = MessageProcessor(redis, graph=graph)

    await p.process(msg(1, "question_unanswered"))
    seen = graph.seen[-1]
    assert seen["current_input"] == "[NO ANSWER]"
    assert seen["interviewer_instruction"] == flow.INSTRUCTIONS["move_on"]

    long_answer = " ".join(["word"] * 70)
    await p.process(msg(2, "candidate_response", long_answer, response_latency_ms="25000"))
    ctx = await p.context_manager.get_context("s1")
    assert ctx["interviewer_instruction"] == ""  # one turn only
    assert ctx["flow"]["unanswered_total"] == 1
    assert ctx["flow"]["response_timings"][-1]["latency_ms"] == 25000
    assert any(f["flag_type"] == "suspicious_timing" for f in ctx["cheat_flags"])


async def test_sweep_ends_idle_interviews_once(redis):
    old = (NOW - timedelta(minutes=30)).isoformat()
    await redis.hset("context:idle", mapping={"interview_ended": "0", "last_updated": old})
    await redis.hset("context:busy", mapping={"interview_ended": "0", "last_updated": NOW.isoformat()})
    await redis.hset("context:done", mapping={"interview_ended": "1", "last_updated": old})

    assert await sweep_inactive(redis, NOW) == ["idle"]
    entries = await redis.xrange("interview:requests")
    assert [(e["session_id"], e["message_type"], e["end_reason"]) for _, e in entries] == [
        ("idle", "end_call", "abandoned")
    ]
    # Another worker's sweep (lock) or a later sweep (already asked) doesn't repeat it
    assert await sweep_inactive(redis, NOW) == []
    await redis.delete("sweep:inactive:lock")
    assert await sweep_inactive(redis, NOW) == []


def test_state_flow_survives_redis_round_trip():
    from services.state_manager import ContextManager

    cm = ContextManager.__new__(ContextManager)
    st = {"session_id": "s1", "flow": {"phase": "closing", "absences": 2}}
    back = cm._deserialize_context(cm._serialize_context(st), "s1")
    assert back["flow"] == {"phase": "closing", "absences": 2}
    assert json.loads(json.dumps(back["flow"]))  # plain JSON


# =============================================================================
# Follow-up checks (brain/verification_probe.py)
# =============================================================================

LONG_ANSWER = " ".join(["word"] * 70)


def _judge(outcome, reason):
    async def judge(probe, policy=None):
        return outcome, reason

    return judge


async def _flagged_answer(p):
    """A long silence, then a long answer: the interviewer is told to probe it."""
    await p.process(msg(1, "candidate_response", LONG_ANSWER, response_latency_ms="24000"))
    return await p.context_manager.get_context("s1")


async def test_flagged_answer_gets_a_follow_up_and_a_good_answer_clears_it(redis, monkeypatch):
    from brain import verification_probe as vp

    graph = EchoGraph()
    p = MessageProcessor(redis, graph=graph)
    ctx = await _flagged_answer(p)
    assert graph.seen[-1]["interviewer_instruction"] == vp.INSTRUCTION
    probe = ctx["flow"]["verification_probes"][0]
    assert (probe["outcome"], probe["question"], probe["words"], probe["latency_ms"]) == ("asked", "ok", 70, 24000)

    monkeypatch.setattr(vp, "judge", _judge("passed", "Gave a concrete example from their project."))
    await p.process(msg(2, "candidate_response", "We used it in the billing service to dedupe events", response_latency_ms="1500"))
    ctx = await p.context_manager.get_context("s1")
    assert graph.seen[-1]["interviewer_instruction"] == ""  # no second probe
    probe = ctx["flow"]["verification_probes"][0]
    assert probe["outcome"] == "passed" and probe["probe_latency_ms"] == 1500
    flag = next(f for f in ctx["cheat_flags"] if f["flag_type"] == "suspicious_timing")
    assert flag["severity"] == "low" and "Cleared" in flag["description"]
    assert ctx["integrity_score"] > 0.99


async def test_follow_up_that_fails_or_goes_unanswered_raises_the_flag(redis, monkeypatch):
    from brain import verification_probe as vp

    p = MessageProcessor(redis, graph=EchoGraph())
    await _flagged_answer(p)
    monkeypatch.setattr(vp, "judge", _judge("failed", "Repeated the first answer without explaining it."))
    await p.process(msg(2, "candidate_response", "It is just the standard way that everyone does it", response_latency_ms="9000"))
    ctx = await p.context_manager.get_context("s1")
    flag = next(f for f in ctx["cheat_flags"] if f["flag_type"] == "suspicious_timing")
    assert flag["severity"] == "high" and "could not explain it" in flag["description"]
    assert "Repeated the first answer" in flag["description"]
    assert ctx["integrity_score"] < 0.95

    await redis.flushdb()
    p = MessageProcessor(redis, graph=EchoGraph())
    await _flagged_answer(p)
    await p.process(msg(2, "question_unanswered"))
    ctx = await p.context_manager.get_context("s1")
    assert ctx["flow"]["verification_probes"][0]["outcome"] == "unanswered"
    flag = next(f for f in ctx["cheat_flags"] if f["flag_type"] == "suspicious_timing")
    assert flag["severity"] == "high" and "did not answer" in flag["description"]


async def test_follow_up_judgement_rules():
    from brain import verification_probe as vp

    base = {"answer": "a", "question": "q", "probe_answer": "yes", "probe_words": 1, "probe_latency_ms": 900}
    assert (await vp.judge(base))[0] == "failed"  # almost no answer

    flow_ = {}
    for n in range(5):
        flow_, instruction = vp.start(flow_, {"flag_id": f"timing-{n}", "turn_number": n}, LONG_ANSWER, 23_000)
        flow_, _ = vp.not_answered(flow_)
    assert len(flow_["verification_probes"]) == vp.POLICY.max_per_interview and instruction == ""

    lines = vp.report_lines({"flow": flow_})
    assert len(lines) == 3 and "did not answer the follow-up" in lines[0]
