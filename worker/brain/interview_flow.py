"""How a study session moves towards its end: time budget, wrap-up, closing,
confirming a goodbye, unanswered questions and returns after a dropped connection.

The rules here are conversation-level and run in the worker before each graph
run. Clock-based rules that need no candidate turn (silence, a dropped
connection) live in the voice agent
(avatar/agents/interview_monitor.py), which reports them as events.

Principle: gentle pacing. Silence gets encouragement, not a penalty; a goodbye
is confirmed before the session ends.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

# =============================================================================
# Policy
# =============================================================================


@dataclass(frozen=True)
class FlowPolicy:
    budget_minutes: float = 30.0
    # Start wrapping up at this share of the budget
    wrap_up_fraction: float = 0.8
    # Safety nets: never normally reached
    hard_stop_minutes: float = 60.0
    max_turns: int = 40
    # Don't wrap up on settled ratings before this
    min_minutes_round1: float = 10.0
    # Candidate's questions and goodbye
    closing_minutes: float = 3.0
    # A skill is settled with this much evidence and a stable rating
    settled_evidence: int = 3
    settled_max_change: float = 0.5
    # Skills below this weight don't hold up the wrap-up
    must_have_weight: float = 0.1


POLICY = FlowPolicy()

EndReason = Literal[
    "completed",  # wrapped up normally
    "candidate_ended",  # candidate confirmed they wanted to stop
    "time_limit",  # hard stop
    "turn_limit",  # safety cap on turns
    "no_response",  # stopped answering (from the voice agent)
    "disconnected",  # connection lost and not back in time (from the voice agent)
    "abandoned",  # no activity at all; closed by the worker's sweep
    "user_ended",  # End button
]

# Interviews that ended before a proper assessment could be made
INCOMPLETE_REASONS = {"no_response", "disconnected", "abandoned"}

# =============================================================================
# Instructions for the buddy (sent outside <learner_input>)
# =============================================================================

INSTRUCTIONS = {
    "wrap_up": (
        "We're near the end of today's study time. Respond warmly to what the learner just said, "
        "tell them they did well today, and ask if there's anything they'd like to go over once "
        "more before you finish. Don't start a new topic."
    ),
    "closing": (
        "You're wrapping up the session. Briefly help with what they asked (one or two short "
        "sentences), then ask if there's anything else. Don't start a new topic."
    ),
    "confirm_end": (
        "The learner may want to stop. Check kindly in one short sentence, for example: "
        "\"Shall we stop here for today?\" Don't ask anything else."
    ),
    "continue_after_confirm": (
        "The learner wants to keep going. Say something encouraging in a few words and carry on "
        "where you left off."
    ),
    "move_on": (
        "The learner didn't answer. That's completely fine: don't repeat the question or make "
        "them feel bad. Reassure them in a few words, give a small hint or a simpler way in, "
        "or offer to explain it together."
    ),
    "replace_question": (
        "The learner's connection dropped and they're back. Welcome them back warmly in one "
        "sentence and pick up the topic again with something easy."
    ),
}

CLOSING_MESSAGES = {
    "completed": "That was a great session! You did really well today. See you next time, bye!",
    "candidate_ended": "Okay, let's stop here for today. Nice work, see you next time!",
    "time_limit": "We've studied for a good while, so let's take a break here. Well done today. Bye!",
    "turn_limit": "That's a lot of learning for one session! Let's stop here. Well done, bye!",
    "no_response": "Looks like you've stepped away, so let's pause here. Come back any time. Bye!",
    "disconnected": "The session has ended. Come back any time!",
    "abandoned": "The session has ended. Come back any time!",
    "user_ended": "Thanks for studying with me today. Bye!",
}

def closing_message(end_reason: str | None) -> str:
    return CLOSING_MESSAGES.get(end_reason or "completed", CLOSING_MESSAGES["completed"])


# =============================================================================
# What the candidate said
# =============================================================================

_END = r"[\s.!]*$"
_GOODBYE = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\b(good)?bye\b",
        r"\bthat'?s (all|it)( from me| for me)?" + _END,
        r"\bi(?: want| would like|'d like| d like) to (stop|end|finish)( (the|this) interview| here| now| early|" + _END + ")",
        r"\blet'?s (stop|end|finish)( (the|this) interview| here| now|" + _END + ")",
        r"\b(end|stop|finish) (the|this|our) (interview|session)\b",
        r"\bthat'?s (all|enough) for (today|now)\b",
        r"\bi'?m done( for today)?" + _END,
        r"\bsee you (later|tomorrow)\b",
        r"\bno (more )?questions\b",
        r"\bthank you for your time\b",
    )
]
_YES = re.compile(
    r"^\s*(yes|yeah|yep|yup|sure|ok(ay)?|please|correct|right|i('?m| am) sure|"
    r"let'?s (end|stop|finish)|end it|go ahead)\b",
    re.IGNORECASE,
)
_NO = re.compile(
    r"\b(no\b|not yet|continue|keep going|sorry|wait|actually|let'?s go on|carry on)",
    re.IGNORECASE,
)
_NOTHING_MORE = re.compile(
    r"^\s*(no|nope|nothing|none|not really|i('?m| am) (good|fine)|that'?s (all|it)|"
    r"i don'?t (have|think)|thank(s| you))\b|"
    r"\b(no (more |other |further )?questions|goodbye|bye)\b",
    re.IGNORECASE,
)
# "No, but I wanted to ask..." is a question, not a goodbye
_ASKING = re.compile(
    r"\?|\b(i (want|wanted|would like|'?d like) to (ask|know)|could you|can you|can i ask|"
    r"what|how|when|where|who|why|which|is there|are there|do you|does the)\b",
    re.IGNORECASE,
)


def wants_to_stop(text: str) -> bool:
    """A goodbye or "I want to stop", as opposed to these words inside an answer.

    "That's all" only counts at the end of what they said ("that's all from me"),
    not mid-answer ("that's all I did on that project"). Even then, ending
    early needs a confirmation (see before_candidate_turn).
    """
    t = text.strip()
    return any(p.search(t) for p in _GOODBYE)


def confirms(text: str) -> bool:
    t = text.strip()
    return bool(_YES.search(t)) and not _NO.search(t)


def has_no_more_questions(text: str) -> bool:
    t = text.strip()
    return bool(_NOTHING_MORE.search(t)) and not _ASKING.search(t)


# =============================================================================
# Flow state (kept in state["flow"])
# =============================================================================


def _flow(state: dict[str, Any]) -> dict[str, Any]:
    flow = dict(state.get("flow") or {})
    flow.setdefault("phase", "interview")  # interview | confirm_end | closing
    flow.setdefault("closing_started_at", None)
    flow.setdefault("unanswered_total", 0)
    flow.setdefault("unanswered_in_a_row", 0)
    flow.setdefault("absences", 0)
    flow.setdefault("level_history", {})
    flow.setdefault("response_timings", [])
    flow.setdefault("wrap_up_reason", None)
    return flow


def _parse(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def elapsed_minutes(state: dict[str, Any], now: datetime) -> float:
    started = _parse(state.get("started_at"))
    return max(0.0, (now - started).total_seconds() / 60) if started else 0.0


# =============================================================================
# Is the assessment good enough to stop?
# =============================================================================


def record_levels(state: dict[str, Any]) -> dict[str, Any]:
    """After a turn: remember each skill's level (last 3) to judge stability."""
    flow = _flow(state)
    tree = state.get("skill_tree") or {}
    history = {k: list(v) for k, v in (flow["level_history"] or {}).items()}
    for skill, level in (tree.get("current_levels") or {}).items():
        values = history.get(skill, [])
        values.append(float(level))
        history[skill] = values[-3:]
    flow["level_history"] = history
    return flow


def skills_settled(state: dict[str, Any], policy: FlowPolicy = POLICY) -> bool:
    """Every must-have skill has enough evidence and a stable rating."""

    tree = state.get("skill_tree") or {}
    weights: dict[str, float] = tree.get("skill_weights") or {}
    evidence: dict[str, int] = tree.get("evidence_counts") or {}
    if not weights:
        return False
    history = _flow(state)["level_history"]
    for skill, weight in weights.items():
        if weight < policy.must_have_weight:
            continue
        if (evidence.get(skill) or 0) < policy.settled_evidence:
            return False
        recent = history.get(skill, [])[-2:]
        if len(recent) < 2 or max(recent) - min(recent) > policy.settled_max_change:
            return False
    return True


# =============================================================================
# Decisions
# =============================================================================


@dataclass
class Decision:
    action: Literal["continue", "conclude"] = "continue"
    instruction: str = ""
    end_reason: str | None = None
    flow: dict[str, Any] = field(default_factory=dict)


def before_candidate_turn(
    state: dict[str, Any], text: str, now: datetime, policy: FlowPolicy = POLICY
) -> Decision:
    """Decide what this candidate turn means for the interview's progress."""
    flow = _flow(state)
    flow["unanswered_in_a_row"] = 0  # they answered something
    elapsed = elapsed_minutes(state, now)
    turn = int(state.get("turn_count") or 0) + 1

    def conclude(reason: str) -> Decision:
        return Decision("conclude", "", reason, flow)

    # Answer to "shall we end here?"
    if flow["phase"] == "confirm_end":
        if confirms(text):
            return conclude("candidate_ended")
        flow["phase"] = "interview"
        instruction = INSTRUCTIONS["continue_after_confirm"]
    else:
        instruction = ""

    # Safety nets
    if elapsed >= policy.hard_stop_minutes:
        return conclude("time_limit")
    if turn >= policy.max_turns:
        return conclude("turn_limit")

    # Closing: the candidate's questions, then goodbye
    if flow["phase"] == "closing":
        since = (now - (_parse(flow["closing_started_at"]) or now)).total_seconds() / 60
        if has_no_more_questions(text) or since >= policy.closing_minutes:
            return conclude("completed")
        return Decision("continue", INSTRUCTIONS["closing"], None, flow)

    # A goodbye before the end: confirm instead of ending on the spot
    if wants_to_stop(text):
        flow["phase"] = "confirm_end"
        return Decision("continue", INSTRUCTIONS["confirm_end"], None, flow)

    # Time to wrap up?
    min_minutes = policy.min_minutes_round1
    if elapsed >= policy.budget_minutes * policy.wrap_up_fraction:
        flow["wrap_up_reason"] = "time"
    elif elapsed >= min_minutes and skills_settled(state, policy):
        flow["wrap_up_reason"] = "assessment_complete"
    if flow["wrap_up_reason"]:
        flow["phase"] = "closing"
        flow["closing_started_at"] = now.isoformat()
        return Decision("continue", INSTRUCTIONS["wrap_up"], None, flow)

    return Decision("continue", instruction, None, flow)


def on_unanswered(state: dict[str, Any]) -> Decision:
    """The voice agent gave up waiting for an answer: move to another question.

    The agent ends the interview after repeated silence; this records it.
    """
    flow = _flow(state)
    flow["unanswered_total"] += 1
    flow["unanswered_in_a_row"] += 1
    return Decision("continue", INSTRUCTIONS["move_on"], None, flow)


def on_returned(state: dict[str, Any]) -> Decision:
    """Back after an absence: the current question is no longer valid."""
    flow = _flow(state)
    flow["absences"] += 1
    return Decision("continue", INSTRUCTIONS["replace_question"], None, flow)


def completion_summary(state: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    """How the interview went, for the report: honest about incomplete ones."""
    flow = _flow(state)
    now = now or datetime.now(UTC)
    reason = state.get("end_reason") or "completed"
    tree = state.get("skill_tree") or {}
    evidence = tree.get("evidence_counts") or {}
    weights = tree.get("skill_weights") or {}
    not_assessed = sorted(s for s in weights if not evidence.get(s))
    timings = [t["latency_ms"] for t in flow["response_timings"]]
    return {
        "end_reason": reason,
        "incomplete": reason in INCOMPLETE_REASONS,
        "minutes": round(elapsed_minutes(state, now), 1),
        "wrap_up_reason": flow["wrap_up_reason"],
        "unanswered_questions": flow["unanswered_total"],
        "absences": flow["absences"],
        "skills_not_assessed": not_assessed,
        "median_response_ms": sorted(timings)[len(timings) // 2] if timings else None,
    }
