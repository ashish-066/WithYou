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
    assert flow.wants_to_stop("I want to stop the session")


def test_goodbye_asks_for_confirmation_then_ends_on_yes():
    d = flow.before_candidate_turn(state(), "I'd like to stop here", NOW)
    assert d.action == "continue" and d.instruction == flow.INSTRUCTIONS["confirm_end"] and d.flow["phase"] == "confirm_end"

    yes = flow.before_candidate_turn(state(flow=d.flow), "Yes, please", NOW)
    assert (yes.action, yes.end_reason) == ("conclude", "candidate_ended")

    no = flow.before_candidate_turn(state(flow=d.flow), "No, let's continue", NOW)
    assert no.action == "continue" and no.flow["phase"] == "interview"
    assert no.instruction == flow.INSTRUCTIONS["continue_after_confirm"]


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

    too_early = state(minutes=8, skill_tree=SETTLED_TREE, flow={"level_history": history})
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

    r = flow.on_returned(state())
    assert r.instruction == flow.INSTRUCTIONS["replace_question"] and r.flow["absences"] == 1


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

    r = await p.process(msg(1, "candidate_response", "I want to stop the session"))
    assert graph.seen[-1]["interviewer_instruction"] == flow.INSTRUCTIONS["confirm_end"] and not r["ended_now"]

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


async def test_processor_moves_on_after_no_answer(redis):
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
