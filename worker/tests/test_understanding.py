"""Phase 3: the gentle evaluator (teach -> ask -> listen -> coach -> adapt)."""

import pytest

import brain.tools.fast.conversation as conversation
from brain import understanding as u
from scoring.models import EvidenceExtraction

POINTS = ["Plants make food from sunlight", "Chlorophyll makes leaves green and catches light", "Plants give out oxygen"]


class FakeExtractor:
    """Stands in for the LLM evidence extractor: verdicts per point id."""

    confidence_threshold = 0.7

    def __init__(self, verdicts):
        self.verdicts = verdicts  # {point_id: ("Yes"|"No"|"Insufficient", quote, confidence)}

    async def extract_single(self, exchange, skill_name, level):
        answer, quote, conf = self.verdicts.get(skill_name, ("Insufficient", "N/A", 0.2))
        return EvidenceExtraction(
            skill_name=skill_name, level=2, answer=answer, evidence=quote, confidence=conf, reasoning="-"
        )


def fresh_map():
    return u.new_map("photosynthesis", "en-IN", POINTS)


async def test_nails_a_misses_b_so_the_next_question_targets_b():
    m = u.asked_about(fresh_map(), "p1")  # buddy asked about p1 (and the answer covers p1 and p2)
    answer = "They use sunlight to make their own food, and the leaves are red because of oxygen"
    verdicts = {
        "p1": ("Yes", "They use sunlight to make their own food", 0.9),
        "p2": ("No", "N/A", 0.8),
    }
    results = await u.assess("How do plants get food?", answer, m["points"], extractor=FakeExtractor(verdicts))
    m = u.apply_assessment(m, results)
    by_id = {p["id"]: p for p in m["points"]}
    assert by_id["p1"]["status"] == "understood" and "sunlight" in by_id["p1"]["evidence"]
    assert m["awaiting"] is None  # p1 is done
    # B (p2) wasn't asked, so it's not a "gap" yet, but A is understood: next is B or C, never A
    nxt = u.next_point({"understanding": m})
    assert nxt["id"] != "p1"

    # Now ask about p2 and they miss it: p2 becomes a gap and is targeted next, before untouched p3
    m = u.asked_about(m, "p2")
    results = await u.assess("Why are leaves green?", "because of oxygen", m["points"],
                             extractor=FakeExtractor({"p2": ("No", "N/A", 0.85)}))
    m = u.apply_assessment(m, results)
    by_id = {p["id"]: p for p in m["points"]}
    assert by_id["p2"]["status"] == "gap" and by_id["p2"]["struggled"]
    m["recent"] = []  # recency aside: the missed idea outranks the untouched one
    assert u.next_point({"understanding": m})["id"] == "p2"


async def test_evidence_must_be_in_the_learners_own_words():
    m = u.asked_about(fresh_map(), "p1")
    # The model claims a quote the learner never said: not counted as understood
    verdicts = {"p1": ("Yes", "plants convert light energy into glucose", 0.95)}
    results = await u.assess("q", "sunlight I think", m["points"], extractor=FakeExtractor(verdicts))
    assert results["p1"] != "understood"


async def test_low_confidence_yes_is_not_understood():
    m = u.asked_about(fresh_map(), "p1")
    verdicts = {"p1": ("Yes", "sunlight", 0.5)}
    results = await u.assess("q", "sunlight", m["points"], extractor=FakeExtractor(verdicts))
    assert results["p1"] == "unclear"


def test_vague_answer_gets_exactly_one_gentle_follow_up():
    state = {"understanding": u.asked_about(fresh_map(), "p2")}
    m, instruction = u.before_reply(state, "maybe the sun?")
    assert instruction == u.FOLLOW_UP_INSTRUCTION.format(point=POINTS[1])
    # Still vague: no second follow-up; the idea is explained kindly instead
    m2, instruction2 = u.before_reply({"understanding": m}, "I don't know")
    assert instruction2 == u.GIVE_IT_KINDLY_INSTRUCTION.format(point=POINTS[1])
    assert m2["followups"]["p2"] == 1
    # A real answer gets no follow-up instruction (it is coached normally)
    _, none = u.before_reply(state, "Chlorophyll is the green stuff that soaks up sunlight")
    assert none == ""


@pytest.mark.parametrize("answer", ["ఏమో, సూర్యుడు?", "അറിയില്ല", "maybe"])
def test_vague_in_telugu_and_malayalam_too(answer):
    assert u.is_vague(answer)


def test_coaching_is_encouragement_gap_hint_never_a_grade():
    rules = u.COACH_RULES.lower()
    assert rules.index("encouragement") < rules.index("gap") < rules.index("hint")
    assert "never say wrong" in rules and "score" in rules
    for instruction in (u.FOLLOW_UP_INSTRUCTION, u.GIVE_IT_KINDLY_INSTRUCTION):
        assert "grade" not in instruction.lower() or "don't grade" in instruction.lower()
    # An answer to the buddy's question is coached, and the coach rules reach the prompt
    assert conversation.turn_mode({"answering_check": True}) == "coach"
    # "maybe the sun?" routes as a question, but it's an answer: coached
    assert conversation.turn_mode({"answering_check": True, "input_classification": "explain_request"}) == "coach"
    assert u.is_answer("explain_request", 0.85) and not u.is_answer("explain_request", 0.95)
    assert not u.is_answer("quiz_request", 0.98) and not u.is_answer("end_signal", 0.95)


async def test_processor_round_trip_keeps_the_map_and_coaches_answers(redis, monkeypatch):
    """Before the reply: answering_check + follow-up; the map survives Redis."""
    from brain.processor import MessageProcessor
    from services.streams import StreamMessage

    seen = []

    class Graph:
        async def ainvoke(self, st, config=None):
            seen.append(dict(st))
            return {**st, "turn_count": (st.get("turn_count") or 0) + 1, "response": "ok"}

    p = MessageProcessor(redis, graph=Graph())
    state = await p.context_manager.get_context("u1")
    state["understanding"] = u.asked_about(fresh_map(), "p2")
    await p.context_manager.update_context("u1", state)

    await p.process(StreamMessage("1-0", "s", "u1", "candidate_response", "maybe the sun?", "", {}))
    assert seen[-1]["answering_check"] is True
    assert seen[-1]["interviewer_instruction"] == u.FOLLOW_UP_INSTRUCTION.format(point=POINTS[1])
    saved = await p.context_manager.get_context("u1")
    assert isinstance(saved["understanding"], dict) and saved["understanding"]["followups"] == {"p2": 1}

    # A request (not an answer) is not coached, even while a question is open
    await p.process(StreamMessage("2-0", "s", "u1", "candidate_response", "quiz me", "", {}))
    assert seen[-1]["answering_check"] is False and seen[-1]["interviewer_instruction"] == ""


def test_session_memory_reaches_the_prompt_for_callbacks():
    m = fresh_map()
    m["points"][0].update(status="understood", struggled=True)
    m["points"][1].update(status="partial", struggled=True)
    memory = conversation.session_memory({"understanding": m})
    assert "Hard at first, now understood (celebrate!): Plants make food from sunlight" in memory
    assert "Still working on it (be encouraging): Chlorophyll" in memory
    assert conversation.session_memory({}) == "Nothing yet."


async def test_starting_topic_is_planned_at_setup_without_a_reply(redis, monkeypatch):
    from brain.processor import MessageProcessor
    from services.streams import StreamMessage

    async def plan(topic, language, llm=None):
        return ["Gravity pulls things down", "Heavier and lighter fall together"]

    monkeypatch.setattr(u, "plan_points", plan)

    class Graph:
        calls = 0

        async def ainvoke(self, st, config=None):
            Graph.calls += 1
            return st

    p = MessageProcessor(redis, graph=Graph())
    r = await p.process(StreamMessage("1-0", "s", "g1", "system_init", "", "", {"language": "en-IN", "topic": "Gravity"}))
    assert r["response"] == "" and Graph.calls == 0  # no reply over the greeting
    state = await p.context_manager.get_context("g1")
    assert state["current_topic"] == "Gravity" and state["understanding"]["topic"] == "Gravity"
    assert [pt["text"] for pt in state["understanding"]["points"]][0] == "Gravity pulls things down"
