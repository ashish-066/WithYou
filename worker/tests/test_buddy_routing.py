"""Phase 1: the brain routes and talks like a study buddy (BUILD_PLAN.md, Phase 1)."""

from datetime import UTC, datetime

import pytest

import brain.tools.fast.conversation as conversation
from brain import interview_flow as flow
from brain.brains.router import PREFILTER_CONFIDENCE_THRESHOLD, run_prefilter

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)


def route(text: str):
    return run_prefilter({"current_input": text, "turn_count": 3})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "text",
    [
        "Teach me about photosynthesis",
        "Can you explain how photosynthesis works",
        "What is photosynthesis?",
        "I want to learn about the French revolution",
        "I don't understand fractions",
    ],
)
def test_topic_request_routes_to_explain_on_the_fast_path(text):
    r = route(text)
    assert r.classification == "explain_request"
    assert r.suggested_brain == "fast"
    # Confident enough that no LLM routing call delays the reply
    assert r.confidence >= PREFILTER_CONFIDENCE_THRESHOLD


@pytest.mark.parametrize("text", ["Hi!", "haha that's a funny one", "I had such a long day at school"])
def test_casual_line_routes_to_chat_on_the_fast_path(text):
    r = route(text)
    assert r.classification == "conversation"
    assert r.suggested_brain == "fast"
    assert r.confidence >= PREFILTER_CONFIDENCE_THRESHOLD


@pytest.mark.parametrize("text", ["Quiz me on that", "Can you test me?", "ask me a question"])
def test_quiz_request_is_a_gentle_check_on_the_fast_path(text):
    r = route(text)
    assert r.classification == "quiz_request" and r.suggested_brain == "fast"


@pytest.mark.parametrize("text", ["Okay that's all for today, bye", "let's stop here", "I'm done for today"])
def test_wrap_up_is_confirmed_then_concludes(text):
    assert route(text).classification == "end_signal"
    state = {"turn_count": 4, "started_at": NOW.isoformat()}
    asked = flow.before_candidate_turn(state, text, NOW)
    assert asked.action == "continue" and asked.instruction == flow.INSTRUCTIONS["confirm_end"]
    done = flow.before_candidate_turn({**state, "flow": asked.flow}, "yes", NOW)
    assert done.action == "conclude" and done.end_reason == "candidate_ended"
    assert "interview" not in flow.closing_message(done.end_reason).lower()


def test_turn_mode_follows_the_router():
    assert conversation.turn_mode({"input_classification": "explain_request"}) == "explain"
    assert conversation.turn_mode({"input_classification": "quiz_request"}) == "check"
    assert conversation.turn_mode({"input_classification": "conversation"}) == "chat"
    assert conversation.turn_mode({}) == "chat"


async def test_prompt_is_the_buddy_persona_with_learner_markers(monkeypatch):
    seen: dict = {}

    class FakeClient:
        async def generate(self, prompt, user_input=None, **kw):
            seen["prompt"], seen["user_input"] = prompt, user_input
            return '{"response_text": "Plants make food from sunlight!", "topics_touched": ["photosynthesis"]}'

    class FakePool:
        def get_fast_client(self):
            return FakeClient()

    async def fake_pool():
        return FakePool()

    monkeypatch.setattr(conversation, "get_llm_pool", fake_pool)
    state = {
        "current_input": "Teach me about photosynthesis",
        "input_classification": "explain_request",
        "messages": [],
        "turn_count": 1,
    }
    out = await conversation.conversation_tool(state)  # type: ignore[arg-type]

    assert out.success and out.data["response_text"] == "Plants make food from sunlight!"
    p = seen["prompt"]
    assert "study buddy" in p and "never a grade" in p
    assert "<learner_input>\nTeach me about photosynthesis\n</learner_input>" in p
    assert "Mode for this turn: explain" in p
    assert "interviewer" not in p.lower() and "candidate" not in p.lower()
    assert seen["user_input"] == "Teach me about photosynthesis"  # firewall sees the raw input
