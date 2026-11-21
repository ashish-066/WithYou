"""How an interview moves towards its end: time budget, wrap-up, closing,
confirming a goodbye, unanswered questions and returns after an absence.

The rules here are conversation-level and run in the worker before each graph
run. Clock-based rules that need no candidate turn (silence, leaving the
camera view, a dropped connection) live in the voice agent
(avatar/agents/interview_monitor.py), which reports them as events.

Principle: nothing the candidate does buys unobserved time. The clock never
stops, and coming back from an absence replaces the current question.
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
    budget_minutes: float = 45.0
    # Start wrapping up at this share of the budget
    wrap_up_fraction: float = 0.8
    # Safety nets: never normally reached
    hard_stop_minutes: float = 60.0
    max_turns: int = 40
    # Don't wrap up on settled ratings before this
    min_minutes_round1: float = 15.0
    min_minutes_coding: float = 20.0
    # Candidate's questions and goodbye
    closing_minutes: float = 3.0
    # A skill is settled with this much evidence and a stable rating
    settled_evidence: int = 3
    settled_max_change: float = 0.5
    # Skills below this weight don't hold up the wrap-up
    must_have_weight: float = 0.1
    # Thinking time that, with a long polished answer, looks like reading
    suspicious_latency_ms: int = 20_000
    suspicious_min_words: int = 60


POLICY = FlowPolicy()

EndReason = Literal[
    "completed",  # wrapped up normally
    "candidate_ended",  # candidate confirmed they wanted to stop
    "time_limit",  # hard stop
    "turn_limit",  # safety cap on turns
    "no_response",  # stopped answering (from the voice agent)
    "left_view",  # out of camera view too long or too often (from the voice agent)
    "disconnected",  # connection lost and not back in time (from the voice agent)
    "abandoned",  # no activity at all; closed by the worker's sweep
    "user_ended",  # End button
]

# Interviews that ended before a proper assessment could be made
INCOMPLETE_REASONS = {"no_response", "left_view", "disconnected", "abandoned"}

# =============================================================================
# Instructions for the interviewer (sent outside <candidate_input>)
# =============================================================================

INSTRUCTIONS = {
    "wrap_up": (
        "Time to wrap up. Respond briefly to the candidate's last answer, tell them that "
        "was your last question, and ask what questions they have for you about the role "
        "or the process. Do not ask another interview question."
    ),
    "closing": (
        "You are in the closing part of the interview. Answer the candidate's question "
        "briefly and honestly (you cannot share results or how they did). Then ask if "
        "they have anything else. Do not ask interview questions."
    ),
    "confirm_end": (
        "The candidate may want to stop the interview early. Ask them to confirm, in one "
        "short sentence, for example: \"It sounds like you'd like to finish. Shall we end "
        "the interview here?\" Do not ask any other question."
    ),
    "continue_after_confirm": (
        "The candidate wants to continue. Acknowledge that briefly and carry on with the "
        "interview where you left off."
    ),
    "move_on": (
        "The candidate did not answer the last question. Do not repeat it or wait for it. "
        "Say briefly that you'll move on, and ask a different question on a different "
        "topic or skill."
    ),
    "move_on_coding": (
        "The candidate did not answer your last question. Do not repeat it. Say briefly "
        "that you'll move on, then ask a different, short question about their current "
        "approach or code."
    ),
    "replace_question": (
        "The candidate was away (out of camera view or disconnected) and has just come "
        "back. Do not return to the previous question: it is no longer valid. Say in one "
        "sentence that you'll continue with a different question, then ask a new question "
        "on a different topic or skill."
    ),
    "replace_question_coding": (
        "The candidate was away (out of camera view or disconnected) and has just come "
        "back. Do not return to your previous question. Say in one sentence that you'll "
        "continue, then ask them to explain, out loud, a specific part of their current "
        "code or approach that you have not discussed yet."
    ),
}

CLOSING_MESSAGES = {
    "completed": (
        "Thank you for your time today. That's the end of our interview. The hiring team "
        "will review it and be in touch. Goodbye!"
    ),
    "candidate_ended": (
        "Alright, we'll end the interview here. Thank you for your time. The hiring team "
        "will be in touch. Goodbye!"
    ),
    "time_limit": (
        "We've reached the time limit, so we'll stop here. Thank you for your time. "
        "The hiring team will be in touch. Goodbye!"
    ),
    "turn_limit": (
        "That brings us to the end of the interview. Thank you for your time. "
        "The hiring team will be in touch. Goodbye!"
    ),
    "no_response": (
        "It seems we've lost you, so we'll stop here. Thank you, and goodbye."
    ),
    "left_view": (
        "As you've been out of view for too long, we have to end the interview here. "
        "Thank you, and goodbye."
    ),
    "disconnected": "The interview has ended. Thank you.",
    "abandoned": "The interview has ended. Thank you.",
    "user_ended": "Thank you for your time. Goodbye!",
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
        r"\b(end|stop|finish) (the|this) interview\b",
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
    """Every must-have skill has enough evidence and a stable rating.

    Coding round: a passing solution and a stated complexity.
    """
    if state.get("interview_mode") == "round2_dsa":
        dsa = state.get("dsa_state") or {}
        last = dsa.get("last_execution_result") or {}
        return bool(
            last.get("tests_total")
            and last.get("pass_rate") == 1.0
            and dsa.get("candidate_complexity_claim")
        )

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
    coding = state.get("interview_mode") == "round2_dsa"

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
    min_minutes = policy.min_minutes_coding if coding else policy.min_minutes_round1
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
    coding = state.get("interview_mode") == "round2_dsa"
    return Decision("continue", INSTRUCTIONS["move_on_coding" if coding else "move_on"], None, flow)


def on_returned(state: dict[str, Any]) -> Decision:
    """Back after an absence: the current question is no longer valid."""
    flow = _flow(state)
    flow["absences"] += 1
    coding = state.get("interview_mode") == "round2_dsa"
    key = "replace_question_coding" if coding else "replace_question"
    return Decision("continue", INSTRUCTIONS[key], None, flow)


def record_timing(
    state: dict[str, Any],
    latency_ms: int | None,
    text: str,
    turn: int,
    now: datetime,
    policy: FlowPolicy = POLICY,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Remember how long the candidate took to start answering.

    Returns the flow and, for a long silence followed by a long answer (the
    pattern of reading an answer from somewhere), an integrity flag.
    """
    flow = _flow(state)
    if latency_ms is None or latency_ms < 0:
        return flow, None
    words = len(text.split())
    flow["response_timings"] = [
        *flow["response_timings"],
        {"turn": turn, "latency_ms": int(latency_ms), "words": words},
    ][-200:]
    if latency_ms >= policy.suspicious_latency_ms and words >= policy.suspicious_min_words:
        seconds = round(latency_ms / 1000)
        return flow, {
            "flag_id": f"timing-{turn}",
            "flag_type": "suspicious_timing",
            "severity": "medium",
            "confidence": 0.5,
            "description": f"Started answering after {seconds} s of silence, then gave a {words}-word answer",
            "timestamp": now.isoformat(),
            "turn_number": turn,
        }
    return flow, None


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
