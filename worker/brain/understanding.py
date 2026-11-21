"""Phase 3: the gentle evaluator. Teach -> ask -> listen -> coach -> adapt.

The understanding map (state["understanding"]) holds the current topic's key
ideas ("points") and what the learner has shown about each, from their own words:

    {"topic": "photosynthesis", "language": "te-IN",
     "points": [{"id": "p1", "text": "...", "status": "unseen|partial|gap|understood",
                 "evidence": "<their words>", "attempts": 0, "struggled": False}],
     "awaiting": "p2" | None,   # the idea the buddy just asked about
     "followups": {"p2": 1},    # gentle follow-ups already asked per idea
     "recent": ["p1", "p2"]}    # ideas asked lately (asked less again soon)

Reused machinery from the interview platform:
- scoring.evidence_extractor: Yes/No/Insufficient + exact quote + confidence,
  confirmed only at >= 0.7 (filter_confirmed_extractions)
- scoring.question_selector: priority = weight * remaining * recency
- the old verification probe's mechanism: a one-turn instruction decided
  before the reply (here: one gentle follow-up for a vague answer)

Timing: the instruction and the mode are decided before the reply; planning the
points and assessing an answer run after the reply was spoken (reply-before-scoring).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from scoring.evidence_extractor import EvidenceExtractor, filter_confirmed_extractions
from scoring.models import (
    CandidateSkillTree,
    LadderLevel,
    QAExchange,
    RoleRequirements,
    SkillRequirement,
    SkillTreeNode,
)
from scoring.question_selector import QuestionSelector

logger = logging.getLogger(__name__)

MAX_FOLLOWUPS_PER_POINT = 1
LANGUAGE_NAMES = {"te-IN": "Telugu", "ml-IN": "Malayalam", "ta-IN": "Tamil", "hi-IN": "Hindi", "en-IN": "English"}

# Priority weights (question selector): a missed idea first, then a half-shown
# one, then one not yet touched
_WEIGHTS = {"gap": 1.0, "partial": 0.8, "unseen": 0.6}

# =============================================================================
# One-turn instructions (sent outside <learner_input>, like interview_flow's)
# =============================================================================

FOLLOW_UP_INSTRUCTION = (
    "The learner's answer was vague or unsure. Don't grade it and don't explain the whole "
    "thing yet. Say something encouraging in a few words (e.g. \"You're close!\"), then ask "
    "exactly ONE short, specific question that nudges them towards this idea: {point}. "
    "Build on the words they just used."
)
GIVE_IT_KINDLY_INSTRUCTION = (
    "The learner is still unsure about this idea: {point}. Don't ask again. Tell them warmly "
    "that it's a tricky one, explain it simply in one or two sentences with an everyday "
    "example, and cheer them on."
)
COACH_RULES = (
    "The learner is answering the question you asked. Reply in this order: (1) encouragement "
    "for what they got right, naming it; (2) the gap, gently, if there is one; (3) a small "
    "hint or the missing piece. Never say wrong, incorrect, or give a score or grade."
)

# =============================================================================
# Before the reply
# =============================================================================

_HEDGES = re.compile(
    r"\b(i think|maybe|not sure|i guess|probably|no idea|i don'?t know|dunno|perhaps)\b|"
    r"ఏమో|అనుకుంటా|తెలియదు|తెలీదు|బహుశా|"
    r"തോന്നുന്നു|അറിയില്ല|ആയിരിക്കും|ഉറപ്പില്ല",
    re.IGNORECASE,
)


def is_vague(answer: str) -> bool:
    """A short or hedged answer that says little ("I think... sunlight?")."""
    words = answer.split()
    if len(words) <= 2:
        return True
    return bool(_HEDGES.search(answer)) and len(words) <= 12


def point_text(state: dict[str, Any], point_id: str | None) -> str | None:
    for p in (state.get("understanding") or {}).get("points") or []:
        if p["id"] == point_id:
            return p["text"]
    return None


def before_reply(state: dict[str, Any], answer: str) -> tuple[dict[str, Any], str]:
    """For a learner turn: the updated map and a one-turn instruction ("" for none).

    If the buddy asked about an idea and the answer is vague, ask exactly one
    gentle follow-up about it; a second vague answer gets the idea explained kindly.
    """
    u = dict(state.get("understanding") or {})
    awaiting = u.get("awaiting")
    if not awaiting or not point_text(state, awaiting) or not is_vague(answer):
        return u, ""
    followups = dict(u.get("followups") or {})
    asked = followups.get(awaiting, 0)
    point = point_text(state, awaiting)
    if asked < MAX_FOLLOWUPS_PER_POINT:
        followups[awaiting] = asked + 1
        u["followups"] = followups
        return u, FOLLOW_UP_INSTRUCTION.format(point=point)
    return u, GIVE_IT_KINDLY_INSTRUCTION.format(point=point)


def is_answer(classification: str, confidence: float) -> bool:
    """While the buddy waits on its question, is this turn the learner's answer?

    Unsure answers often end in "?" ("maybe the sun?"), which alone routes as a
    question. Only clear requests take over: quiz me, goodbye, a summary, or an
    explicit "explain / what is" (strong match).
    """
    if classification in ("quiz_request", "end_signal", "report_request", "deep_analysis"):
        return False
    if classification == "explain_request":
        return confidence < 0.9
    return True


def answering_a_check(state: dict[str, Any]) -> bool:
    """The buddy asked about an idea and this turn is the learner's answer."""
    return bool((state.get("understanding") or {}).get("awaiting"))


# =============================================================================
# What to ask or teach next (question selector priority formula)
# =============================================================================


def next_point(state: dict[str, Any]) -> dict[str, Any] | None:
    """The idea to gently check next: missed > half-shown > untouched, not one just asked."""
    u = state.get("understanding") or {}
    open_points = [p for p in u.get("points") or [] if p["status"] != "understood"]
    if not open_points:
        return None
    tree = CandidateSkillTree(
        candidate_id="learner",
        session_id=str(state.get("session_id") or ""),
        role_id=str(u.get("topic") or ""),
        skills={p["id"]: SkillTreeNode(skill_name=p["id"], current_level=0) for p in open_points},
    )
    requirements = RoleRequirements(
        title=str(u.get("topic") or ""),
        skills=[SkillRequirement(skill_name=p["id"], weight=_WEIGHTS[p["status"]]) for p in open_points],
    )
    ranked = QuestionSelector(llm=object()).calculate_skill_priorities(
        tree, requirements, recent_skills=list(u.get("recent") or [])
    )
    best = ranked[0][0]
    return next(p for p in open_points if p["id"] == best)


def check_guidance(state: dict[str, Any]) -> str | None:
    """Text for the reply prompt's <what_to_check_next>."""
    p = next_point(state)
    return p["text"] if p else None


# =============================================================================
# After the reply
# =============================================================================

PLAN_PROMPT = """List the 3 or 4 key ideas a school learner should understand about this topic,
as short plain statements (max 15 words each), in {language}{script_note}.

Topic: {topic}

Respond with JSON only: {{"points": ["idea 1", "idea 2", "idea 3"]}}"""


class FastLLM:
    """The fast pool (Sarvam-105B first, ~1 s; Gemini fallback) behind the
    `ainvoke(prompt)` interface the scoring modules expect. The scoring client
    (gemini-3.5-flash) took 17-21 s or timed out here, holding the session lock."""

    async def ainvoke(self, prompt: str) -> str:
        from brain.models.llm_pool import get_llm_pool

        pool = await get_llm_pool()
        return await pool.get_fast_client().generate(prompt, temperature=0.1, max_tokens=600)


async def plan_points(topic: str, language: str, llm: Any | None = None) -> list[str]:
    """The key ideas of a topic (one model call)."""
    from core.llm_text import message_text

    name = LANGUAGE_NAMES.get(language, "English")
    note = "" if name == "English" else f" ({name} script; English technical terms are fine)"
    llm = llm or FastLLM()
    response = await llm.ainvoke(PLAN_PROMPT.format(topic=topic, language=name, script_note=note))
    text = message_text(response)
    match = re.search(r"\{.*\}", text, re.S)
    data = json.loads(match.group(0)) if match else {}
    return [str(p).strip() for p in data.get("points", []) if str(p).strip()][:4]


def new_map(topic: str, language: str, points: list[str]) -> dict[str, Any]:
    return {
        "topic": topic,
        "language": language,
        "points": [
            {"id": f"p{i}", "text": t, "status": "unseen", "evidence": "", "attempts": 0, "struggled": False}
            for i, t in enumerate(points, 1)
        ],
        "awaiting": None,
        "followups": {},
        "recent": [],
    }


async def assess(
    question: str,
    answer: str,
    points: list[dict[str, Any]],
    extractor: EvidenceExtractor | None = None,
) -> dict[str, str]:
    """For each open idea: understood (confirmed Yes with a quote), gap (No), or
    unclear (Insufficient). Returns {point_id: "understood"|"gap"|"unclear"}, plus
    the quotes in {point_id + ":quote": text}."""
    extractor = extractor or EvidenceExtractor(llm=FastLLM(), confidence_threshold=0.7)
    exchange = QAExchange(turn_number=0, interviewer_question=question, candidate_response=answer)
    open_points = [p for p in points if p["status"] != "understood"]

    async def one(p):
        level = LadderLevel(
            level=2,
            binary_question=f"Does the learner's answer show they understand this idea: {p['text']}?",
            evidence_hints=[p["text"]],
            example_yes="",
            example_no="",
        )
        return p["id"], await extractor.extract_single(exchange, p["id"], level)

    results = await asyncio.gather(*(one(p) for p in open_points))
    out: dict[str, str] = {}
    for pid, ex in results:
        confirmed = filter_confirmed_extractions([ex], extractor.confidence_threshold)
        # The quote must really be in what they said (no invented evidence)
        if confirmed and ex.evidence and ex.evidence != "N/A" and _in_answer(ex.evidence, answer):
            out[pid] = "understood"
            out[pid + ":quote"] = ex.evidence
        elif ex.answer == "No" and ex.confidence >= extractor.confidence_threshold:
            out[pid] = "gap"
        else:
            out[pid] = "unclear"
    return out


def _in_answer(quote: str, answer: str) -> bool:
    norm = lambda s: re.sub(r"[\s\W_]+", " ", s, flags=re.UNICODE).strip().lower()  # noqa: E731
    return norm(quote) in norm(answer)


def apply_assessment(u: dict[str, Any], results: dict[str, str]) -> dict[str, Any]:
    """Update the map with an assessment of the answer to `u["awaiting"]`."""
    u = json.loads(json.dumps(u))  # deep copy
    awaiting = u.get("awaiting")
    for p in u["points"]:
        verdict = results.get(p["id"])
        if verdict == "understood":
            p["status"] = "understood"
            p["evidence"] = results.get(p["id"] + ":quote", "")
        elif p["id"] == awaiting:
            # Only the idea that was asked about counts as missed or half-shown
            p["attempts"] += 1
            p["struggled"] = True
            p["status"] = "gap" if verdict == "gap" else "partial"
    target = next((p for p in u["points"] if p["id"] == awaiting), None)
    if target is None or target["status"] == "understood":
        u["awaiting"] = None
    return u


def asked_about(u: dict[str, Any], point_id: str) -> dict[str, Any]:
    """The buddy just asked a check question about `point_id`."""
    u = dict(u)
    u["awaiting"] = point_id
    u["recent"] = [*[r for r in u.get("recent") or [] if r != point_id], point_id][-3:]
    return u
