"""'Just talk' mode (emotional buddy) and crisis safety."""

import pytest

import brain.tools.fast.conversation as conversation
from brain import talk
from brain import understanding as u
from brain.processor import MessageProcessor
from services.streams import StreamMessage


@pytest.mark.parametrize(
    "text",
    [
        "I just want to die",
        "sometimes I think about killing myself... I mean kill myself",
        "I don't want to live anymore",
        "everyone would be better off without me",
        "నాకు చనిపోవాలని ఉంది",
        "బతకాలని లేదు",
        "എനിക്ക് മരിക്കണം",
        "ഇനി ജീവിക്കണ്ട",
        "I've been thinking about suicide",
    ],
)
def test_crisis_language_is_noticed(text):
    assert talk.in_crisis(text)


@pytest.mark.parametrize(
    "text",
    [
        "this exam is killing me",
        "I could die laughing at that joke",
        "the deadline is tomorrow",
        "photosynthesis is how plants make food",
        "నాకు పరీక్ష అంటే భయం",
        "ഇന്ന് ഭയങ്കര ബോറാണ്",
    ],
)
def test_everyday_words_are_not_a_crisis(text):
    assert not talk.in_crisis(text)


class Graph:
    def __init__(self):
        self.seen = []

    async def ainvoke(self, st, config=None):
        self.seen.append(dict(st))
        return {**st, "turn_count": (st.get("turn_count") or 0) + 1, "response": "ok"}


def msg(n, kind, content="", **raw):
    return StreamMessage(f"{n}-0", "s", "t1", kind, content, "", raw)


async def test_crisis_gets_the_safety_reply_in_any_mode_and_never_ends_the_session(redis):
    graph = Graph()
    p = MessageProcessor(redis, graph=graph)
    await p.process(msg(1, "system_init", language="te-IN", mode="study"))
    # Even worded as a goodbye, a crisis turn doesn't end the session
    await p.process(msg(2, "candidate_response", "నాకు చనిపోవాలని ఉంది, బై"))
    seen = graph.seen[-1]
    assert seen["interviewer_instruction"] == talk.CRISIS_INSTRUCTION
    assert "14416" in talk.CRISIS_INSTRUCTION and "112" in talk.CRISIS_INSTRUCTION
    assert not seen.get("interview_ended") and seen["crisis_flagged"] is True


async def test_talk_mode_skips_study_bookkeeping_and_uses_the_listener(redis):
    graph = Graph()
    p = MessageProcessor(redis, graph=graph)
    await p.process(msg(1, "system_init", language="ml-IN", mode="talk"))
    state = await p.context_manager.get_context("t1")
    assert state["session_mode"] == "talk"
    # Even with an open study question in the map, talk mode doesn't coach or follow up
    state["understanding"] = u.asked_about(u.new_map("x", "ml-IN", ["a", "b"]), "p1")
    await p.context_manager.update_context("t1", state)
    await p.process(msg(2, "candidate_response", "maybe"))
    assert graph.seen[-1]["answering_check"] is False and graph.seen[-1]["interviewer_instruction"] == ""

    # Silence gets the talk-mode "I'm here" line, not "let me give you a hint"
    await p.process(msg(3, "question_unanswered"))
    assert graph.seen[-1]["interviewer_instruction"] == talk.TALK_INSTRUCTIONS["move_on"]


async def test_talk_prompt_is_a_listener_not_a_teacher(monkeypatch):
    seen = {}

    class Client:
        async def generate(self, prompt, user_input=None, **kw):
            seen["prompt"] = prompt
            return '{"response_text": "That sounds really tiring."}'

    class Pool:
        def get_fast_client(self):
            return Client()

    async def pool():
        return Pool()

    monkeypatch.setattr(conversation, "get_llm_pool", pool)
    out = await conversation.conversation_tool(
        {"current_input": "exams are stressing me out", "session_mode": "talk", "language": "en-IN", "messages": []}
    )
    assert out.success and out.data["response_text"] == "That sounds really tiring."
    assert "good listener" in seen["prompt"] and "not a therapist" in seen["prompt"]
    assert "Mode for this turn" not in seen["prompt"]  # no study modes


async def test_talk_goodbye_and_end_card_with_helpline_after_a_crisis(monkeypatch):
    import brain.graph as graph
    from brain.services.reply_publisher import bind_reply_publisher, reset_reply_publisher
    from brain.tools.slow import report_generator

    spoken = []

    async def publish(text):
        spoken.append(text)

    class Down:
        async def generate(self, *a, **k):
            raise RuntimeError("no model")

    class Pool:
        def get_fast_client(self):
            return Down()

        def get_slow_client(self):
            return Down()

    async def pool():
        return Pool()

    monkeypatch.setattr(report_generator, "get_llm_pool", pool)
    token = bind_reply_publisher(publish)
    try:
        out = await graph.conclude_interview_node(
            {"session_id": "t", "end_reason": "candidate_ended", "language": "te-IN",
             "session_mode": "talk", "crisis_flagged": True, "messages": []}  # type: ignore[arg-type]
        )
    finally:
        reset_reply_publisher(token)
    assert spoken == [talk.TALK_GOODBYES["te-IN"]]
    card = out["descriptive_report"]
    assert card["mode"] == "talk" and "14416" in card["help"]
    assert card["covered"] == [] and card["improved"] == []  # nothing private on the card


async def test_mood_from_home_reaches_the_talk_prompt(redis, monkeypatch):
    graph = Graph()
    p = MessageProcessor(redis, graph=graph)
    await p.process(msg(1, "system_init", language="te-IN", mode="talk", topic="ఎగ్జామ్ భయం"))
    state = await p.context_manager.get_context("t1")
    assert state["mood"] == "ఎగ్జామ్ భయం" and "understanding" not in state  # no study plan in talk mode
