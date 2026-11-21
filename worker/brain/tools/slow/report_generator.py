"""The end-of-session recap, for the learner (the old hiring report, reskinned).

Two outputs, under the report writer's original entry points so every caller
(conclude node, retry sweep, report request, Postgres save) keeps working:

1. generate_descriptive_report -> the recap card, written warmly in the session's
   language: what we covered, where you got sharper, one thing for next time.
   No scores, no judgments. Falls back to a plain recap built from the
   understanding map when no model answers, so there is always a card.
2. generate_analytics_report -> structured data from the understanding map
   (topic, ideas and their status, ideas that were hard at first and then clicked).
"""

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from brain.models.llm_pool import get_llm_pool
from brain.models.schemas import FilteredToolOutput
from brain.state import InterviewState

logger = logging.getLogger(__name__)

LANGUAGE_NAMES = {"te-IN": "Telugu", "ml-IN": "Malayalam", "en-IN": "English"}

# =============================================================================
# Prompt
# =============================================================================

RECAP_PROMPT = """You are a warm study buddy writing a short recap card for the learner you just
studied with. Write it to them ("you"), in simple, friendly {language}{script_note}.

What we studied, with what the learner showed:
{understanding}

The whole conversation (Learner = them, Buddy = you):
{conversation_summary}

Rules:
- Only use what really happened in the conversation. Don't invent progress.
- Celebrate effort and what clicked. Where something is still shaky, frame it as
  "next time we can..." - never as a failure.
- No scores, grades, percentages or ranking words.
- Short: each list item max 15 words.

Respond with JSON only:
{{
  "title": "a short friendly title",
  "summary": "one or two warm sentences about today's session",
  "covered": ["what we studied together", "..."],
  "improved": ["something they got better at or that clicked during the session", "..."],
  "next_time": "one gentle suggestion for next time"
}}"""

# Plain recap when no model is available (from the understanding map)
FALLBACK = {
    "en-IN": {
        "title": "What we studied today",
        "summary": "Nice work today! Here is what we went through together.",
        "improved": "You worked through it until it clicked",
        "next_time": "Next time we can go a little deeper.",
        "next_open": "Next time we can look again at: {idea}",
    },
    "te-IN": {
        "title": "ఈ రోజు మనం నేర్చుకున్నది",
        "summary": "ఈ రోజు బాగా చేశావు! మనం కలిసి నేర్చుకున్నవి ఇవే.",
        "improved": "మొదట కష్టంగా అనిపించినా, చివరికి అర్థమైంది",
        "next_time": "తర్వాత ఇంకొంచెం లోతుగా నేర్చుకుందాం.",
        "next_open": "తర్వాత మళ్ళీ చూద్దాం: {idea}",
    },
    "ml-IN": {
        "title": "ഇന്ന് നമ്മൾ പഠിച്ചത്",
        "summary": "ഇന്ന് നന്നായി ചെയ്തു! നമ്മൾ ഒരുമിച്ച് പഠിച്ചത് ഇതാ.",
        "improved": "ആദ്യം ബുദ്ധിമുട്ടായിരുന്നു, പിന്നെ ശരിയായി",
        "next_time": "അടുത്ത തവണ കുറച്ചുകൂടി ആഴത്തിൽ പഠിക്കാം.",
        "next_open": "അടുത്ത തവണ ഒന്നുകൂടി നോക്കാം: {idea}",
    },
}

# =============================================================================
# Recap card (descriptive report)
# =============================================================================


async def generate_descriptive_report(state: InterviewState, input_data: Any = None) -> FilteredToolOutput:
    """The learner's recap card (see module docstring)."""
    language = str(state.get("language") or "en-IN")
    try:
        pool = await get_llm_pool()
        data = _build_report_prompt_data(state, await _load_full_transcript(state))
        name = LANGUAGE_NAMES.get(language, "English")
        prompt = RECAP_PROMPT.format(
            language=name,
            script_note="" if name == "English" else f", in {name} script",
            understanding=_format_understanding(state),
            conversation_summary=data["conversation_summary"],
        )
        recap = _parse_recap(await _generate(pool, prompt, max_tokens=900))
        source = "llm"
    except Exception as e:
        logger.warning(f"Recap: no model answered ({e}); using the plain recap")
        recap, source = fallback_recap(state), "fallback"
    recap["language"] = language
    return FilteredToolOutput(
        success=True,
        data=recap,
        confidence=0.85 if source == "llm" else 0.5,
        source=source,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def fallback_recap(state: InterviewState) -> dict[str, Any]:
    """A recap from the understanding map alone (no model)."""
    words = FALLBACK.get(str(state.get("language") or "en-IN"), FALLBACK["en-IN"])
    u = state.get("understanding") or {}
    points = u.get("points") or []
    clicked = [p for p in points if p.get("status") == "understood"]
    open_ = [p for p in points if p.get("status") != "understood"]
    covered = [p["text"] for p in clicked] or ([u["topic"]] if u.get("topic") else [])
    covered = covered or list(state.get("topics_covered") or [])[:4]
    return {
        "title": words["title"],
        "summary": words["summary"],
        "covered": covered[:4],
        "improved": [f"{words['improved']}: {p['text']}" for p in clicked if p.get("struggled")][:3],
        "next_time": words["next_open"].format(idea=open_[0]["text"]) if open_ else words["next_time"],
    }


def _parse_recap(text: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError("no JSON in the recap answer")
    data = json.JSONDecoder(strict=False).decode(match.group(0))
    if not str(data.get("summary") or "").strip():
        raise ValueError("recap without a summary")
    as_list = lambda v: [str(x).strip() for x in (v or []) if str(x).strip()][:4]  # noqa: E731
    return {
        "title": str(data.get("title") or "").strip(),
        "summary": str(data["summary"]).strip(),
        "covered": as_list(data.get("covered")),
        "improved": as_list(data.get("improved")),
        "next_time": str(data.get("next_time") or "").strip(),
    }


# =============================================================================
# Structured data (analytics report)
# =============================================================================


async def generate_analytics_report(state: InterviewState, input_data: Any = None) -> FilteredToolOutput:
    """Topic and ideas from the understanding map (no model call, no scores)."""
    u = state.get("understanding") or {}
    ideas = [{"text": p.get("text", ""), "status": p.get("status", "unseen")} for p in u.get("points") or []]
    data = {
        "topic": u.get("topic") or state.get("current_topic"),
        "language": state.get("language"),
        "ideas": ideas,
        "covered": sum(1 for i in ideas if i["status"] == "understood"),
        "clicked_after_struggle": [
            p.get("text", "") for p in u.get("points") or [] if p.get("struggled") and p.get("status") == "understood"
        ],
        "topics_touched": list(state.get("topics_covered") or []),
        "total_turns": state.get("turn_count", 0),
    }
    return FilteredToolOutput(
        success=True, data=data, confidence=1.0, source="understanding_map",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


# =============================================================================
# Helpers
# =============================================================================

# The prompt gets the whole conversation, up to these limits (characters).
# A very long session keeps its opening and as much of the rest as fits.
MAX_MESSAGE_CHARS = 2_000
MAX_CONVERSATION_CHARS = 60_000


async def _load_full_transcript(state: InterviewState) -> list[dict[str, Any]] | None:
    """The full conversation from Redis (state["messages"] holds only the last 10)."""
    session_id = state.get("session_id")
    if not session_id:
        return None
    try:
        from core.redis import get_redis_client
        from services.transcript import load_transcript

        return await load_transcript(await get_redis_client(), session_id)
    except Exception as e:
        logger.warning(f"Recap: full transcript unavailable for {session_id}, using recent messages: {e}")
        return None


def _format_conversation(messages: list[dict[str, Any]]) -> str:
    lines = []
    for msg in messages:
        role = msg.get("role")
        if role not in ("user", "human", "assistant"):
            continue
        content = (msg.get("content") or "").strip()
        if not content:
            continue
        if len(content) > MAX_MESSAGE_CHARS:
            content = content[:MAX_MESSAGE_CHARS] + " [...]"
        lines.append(f"{'Buddy' if role == 'assistant' else 'Learner'}: {content}")

    if sum(len(line) + 1 for line in lines) <= MAX_CONVERSATION_CHARS:
        return "\n".join(lines) or "No conversation recorded."

    # Too long: keep the opening (a quarter of the budget) and the rest from the end
    head: list[str] = []
    used = 0
    for line in lines:
        if used + len(line) + 1 > MAX_CONVERSATION_CHARS // 4:
            break
        head.append(line)
        used += len(line) + 1
    tail: list[str] = []
    for line in reversed(lines[len(head):]):
        if used + len(line) + 1 > MAX_CONVERSATION_CHARS:
            break
        tail.append(line)
        used += len(line) + 1
    tail.reverse()
    omitted = len(lines) - len(head) - len(tail)
    return "\n".join([*head, f"[... {omitted} messages left out for length ...]", *tail])


def _build_report_prompt_data(
    state: InterviewState, transcript: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Prompt inputs: the whole conversation (full transcript if available)."""
    messages = transcript if transcript else list(state.get("messages") or [])
    return {"conversation_summary": _format_conversation(messages)}


def _format_understanding(state: InterviewState) -> str:
    u = state.get("understanding") or {}
    if not u.get("points"):
        topics = ", ".join(state.get("topics_covered") or []) or "(no specific topic)"
        return f"Topics touched: {topics}"
    lines = [f"Topic: {u.get('topic')}"]
    for p in u["points"]:
        note = {"understood": "showed they understand it", "partial": "partly there",
                "gap": "still working on it", "unseen": "not discussed yet"}.get(p.get("status"), "")
        if p.get("struggled") and p.get("status") == "understood":
            note += " (it was hard at first, then it clicked)"
        lines.append(f"- {p.get('text')}: {note}")
    return "\n".join(lines)


async def _generate(pool: Any, prompt: str, max_tokens: int) -> str:
    """The fast model (Sarvam first: best for Malayalam/Telugu), then the slow one."""
    try:
        return await pool.get_fast_client().generate(prompt, max_tokens=max_tokens)
    except Exception as e:
        logger.warning(f"Recap: fast model failed ({e}); trying the slow model")
        return await pool.get_slow_client().generate(prompt, max_tokens=max_tokens)
