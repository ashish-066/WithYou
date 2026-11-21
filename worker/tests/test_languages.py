"""Phase 2: Sarvam brain with Gemini fallback, Malayalam/Telugu sessions, language switching."""

from datetime import UTC, datetime

import pytest

import brain.models.llm_pool as llm_pool
import brain.tools.fast.conversation as conversation
from brain import interview_flow as flow
from brain.brains.router import run_prefilter
from brain.processor import MessageProcessor
from core.config import settings
from services.streams import StreamMessage

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)


# =============================================================================
# LLM pool: Sarvam first, Gemini on failure
# =============================================================================


class _FakeGemini:
    """Stands in for google.genai: records calls, returns a fixed answer."""

    def __init__(self):
        self.calls = 0
        outer = self

        class _Models:
            async def generate_content(self, model, contents, config):
                outer.calls += 1
                return type("R", (), {"text": "from gemini"})()

        self.aio = type("Aio", (), {"models": _Models()})()


def _client(brain_type="fast"):
    return llm_pool.LLMClient(
        client=_FakeGemini(), config=llm_pool.LLMConfig(model_name="gemini-x"),
        client_id=0, brain_type=brain_type,
    )


@pytest.fixture
def sarvam_on(monkeypatch):
    monkeypatch.setattr(settings, "sarvam_api_key", "test-key")
    monkeypatch.setattr(settings, "fast_llm_provider", "sarvam")


async def test_fast_replies_come_from_sarvam_first(sarvam_on, monkeypatch):
    async def sarvam(prompt, system, temperature, max_tokens):
        return "from sarvam"

    monkeypatch.setattr(llm_pool, "sarvam_generate", sarvam)
    c = _client()
    assert await c.generate("hi") == "from sarvam"
    assert c.client.calls == 0  # Gemini not called


async def test_sarvam_failure_falls_back_to_gemini(sarvam_on, monkeypatch):
    async def broken(*a, **k):
        raise TimeoutError("slow")

    monkeypatch.setattr(llm_pool, "sarvam_generate", broken)
    c = _client()
    assert await c.generate("hi") == "from gemini"
    assert c.client.calls == 1


async def test_analysis_stays_on_gemini(sarvam_on, monkeypatch):
    async def sarvam(*a, **k):
        raise AssertionError("slow brain must not use Sarvam")

    monkeypatch.setattr(llm_pool, "sarvam_generate", sarvam)
    assert await _client("slow").generate("analyse") == "from gemini"


async def test_sarvam_request_turns_reasoning_off_and_reads_the_answer(sarvam_on, monkeypatch):
    sent = {}

    class FakeHTTP:
        async def post(self, url, headers, json):
            sent.update(json)
            body = {"choices": [{"message": {"content": "\n  നമസ്കാരം  ", "reasoning_content": "…"}}]}
            return type("Resp", (), {"raise_for_status": lambda self: None, "json": lambda self: body})()

    monkeypatch.setattr(llm_pool, "_sarvam_http", FakeHTTP())
    assert await llm_pool.sarvam_generate("p", "sys", 0.7, 512) == "നമസ്കാരം"
    assert sent["model"] == "sarvam-105b" and sent["reasoning_effort"] == "none"
    assert sent["messages"][0] == {"role": "system", "content": "sys"}


# =============================================================================
# Language of the session
# =============================================================================


def msg(n, message_type, content="", **raw):
    return StreamMessage(f"{n}-0", "s", "lang1", message_type, content, "", raw)


class EchoGraph:
    def __init__(self):
        self.seen = []

    async def ainvoke(self, st, config=None):
        self.seen.append(dict(st))
        out = {**st, "turn_count": (st.get("turn_count") or 0) + 1, "response": "ok"}
        if st.get("interview_ended"):
            out["response"] = flow.closing_message(st.get("end_reason"), st.get("language"))
        return out


async def test_language_follows_setup_then_what_the_learner_speaks(redis):
    graph = EchoGraph()
    p = MessageProcessor(redis, graph=graph)

    r = await p.process(msg(1, "system_init", language="ml-IN"))
    assert r["response"] == "" and graph.seen == []  # setup only: no reply over the greeting
    assert (await p.context_manager.get_context("lang1"))["language"] == "ml-IN"

    await p.process(msg(2, "candidate_response", "నమస్కారం", language="te-IN"))
    assert graph.seen[-1]["language"] == "te-IN"  # switched to Telugu
    await p.process(msg(3, "candidate_response", "hello", language="xx-XX"))
    assert graph.seen[-1]["language"] == "te-IN"  # unknown codes are ignored


def test_prompt_language_rule_follows_the_session(monkeypatch):
    monkeypatch.setattr(settings, "buddy_language", "ml-IN")
    assert "Reply in Telugu." in conversation.language_rule({"language": "te-IN"})
    assert "Reply in Malayalam." in conversation.language_rule({})
    assert "Reply in English." in conversation.language_rule({"language": "en-IN"})
    assert "switch" in conversation.language_rule({"language": "te-IN"})


@pytest.mark.parametrize(
    "text,expected",
    [
        ("ప్రకాశసంశ్లేషణ అంటే ఏమిటి? నాకు చెప్పు", "explain_request"),
        ("പ്രകാശസംശ്ലേഷണം എന്താണെന്ന് പറഞ്ഞുതരാമോ?", "explain_request"),
        ("నన్ను క్విజ్ చేయి", "quiz_request"),
        ("എന്നോട് ഒരു ചോദ്യം ചോദിക്കൂ", "quiz_request"),
        ("సరే, ఈ రోజుకి చాలు, బై", "end_signal"),
        ("ഇന്നത്തേക്ക് മതി, ബൈ", "end_signal"),
    ],
)
def test_telugu_and_malayalam_intents(text, expected):
    r = run_prefilter({"current_input": text, "turn_count": 3})  # type: ignore[arg-type]
    assert r.classification == expected
    assert r.suggested_brain == ("end" if expected == "end_signal" else "fast")


@pytest.mark.parametrize(
    "bye,yes,lang",
    [("సరే, ఈ రోజుకి చాలు, బై", "అవును", "te-IN"), ("ഇന്നത്തേക്ക് മതി, ബൈ", "ശരി", "ml-IN")],
)
def test_native_goodbye_is_confirmed_then_ends_in_that_language(bye, yes, lang):
    state = {"turn_count": 4, "started_at": NOW.isoformat(), "language": lang}
    asked = flow.before_candidate_turn(state, bye, NOW)
    assert asked.instruction == flow.INSTRUCTIONS["confirm_end"]
    done = flow.before_candidate_turn({**state, "flow": asked.flow}, yes, NOW)
    assert done.action == "conclude"
    goodbye = flow.closing_message(done.end_reason, lang)
    script = range(0x0C00, 0x0C80) if lang == "te-IN" else range(0x0D00, 0x0D80)
    assert any(ord(ch) in script for ch in goodbye)


async def test_goodbye_is_spoken_before_the_report_is_written(monkeypatch):
    import brain.graph as graph
    from brain.services.reply_publisher import bind_reply_publisher, reset_reply_publisher

    events = []

    async def report(state):
        events.append("report")
        return type("R", (), {"success": True, "data": {"summary": "x"}})()

    monkeypatch.setattr(graph, "generate_descriptive_report", report)
    monkeypatch.setattr(graph, "generate_analytics_report", report)

    async def publish(text):
        events.append(("spoken", text))

    token = bind_reply_publisher(publish)
    try:
        out = await graph.conclude_interview_node(
            {"session_id": "s", "end_reason": "candidate_ended", "language": "te-IN"}  # type: ignore[arg-type]
        )
    finally:
        reset_reply_publisher(token)
    assert events[0] == ("spoken", flow.closing_message("candidate_ended", "te-IN"))
    assert events[1:] == ["report", "report"]
    assert out["interview_ended"] and out["report_status"] == "completed"


# =============================================================================
# Replies in Indic scripts survive imperfect JSON from the model
# =============================================================================


@pytest.mark.parametrize(
    "raw,expected",
    [
        ('{"response_text": "ఖచ్చితంగా, మనం కలిసి నేర్చుకుందాం."}', "ఖచ్చితంగా, మనం కలిసి నేర్చుకుందాం."),
        ('{\n "response_text": "ശരി,\nനമുക്ക് പഠിക്കാം."}', "ശരി,\nനമുക്ക് പഠിക്കാം."),
        ('Sure!\n```json\n{"response_text": "ശരി, നമുക്ക് പഠിക്കാം."}\n```', "ശരി, നമുക്ക് പഠിക്കാം."),
        ('{"response_text": "మనం కలిసి \\"server\\" గురించి', 'మనం కలిసి "server" గురించి'),
    ],
)
def test_indic_reply_is_never_mojibake(raw, expected):
    # Regression: the fallback used .decode("unicode_escape"), turning Telugu into "à°à°..."
    text = conversation._parse_conversation_response(raw).response_text
    assert text == expected
    assert "à" not in text
