"""Hybrid Brain Router combining fast pre-filter with LLM routing.

Implements a two-stage routing strategy:
1. Fast pre-filter: Regex-based pattern matching with confidence scoring
2. LLM router: Semantic understanding for ambiguous cases

This ensures low latency for obvious cases while maintaining accuracy
for complex routing decisions.
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from brain.models.schemas import PrefilterResult, RoutingDecision
from brain.state import DFAState, DFAStateType, InterviewState

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

# Confidence threshold for pre-filter (below this, use LLM router)
PREFILTER_CONFIDENCE_THRESHOLD = 0.85

# Confidence scores for different match types
CONFIDENCE_EXACT_MATCH = 0.95  # Strong keyword match
CONFIDENCE_PATTERN_MATCH = 0.85  # Regex pattern match
CONFIDENCE_WEAK_MATCH = 0.70  # Single weak indicator
CONFIDENCE_DEFAULT = 0.90  # Default conversational flow (Fast Brain)


# =============================================================================
# DFA Transition Rules
# =============================================================================


@dataclass
class DFATransition:
    """A transition in the DFA state machine."""

    from_state: DFAStateType
    to_state: DFAStateType
    condition: str  # Human-readable condition description
    timestamp: str


# State transition table (deterministic)
TRANSITION_TABLE: dict[DFAStateType, dict[str, DFAStateType]] = {
    "idle": {
        "user_input": "routing",
        "timeout": "concluding",
    },
    "routing": {
        "is_conversation": "fast_processing",
        "is_task": "slow_processing",
        "is_end_signal": "concluding",
    },
    "fast_processing": {
        "needs_tool": "tool_executing",
        "response_ready": "responding",
        "interview_end": "concluding",
    },
    "slow_processing": {
        "needs_tool": "tool_executing",
        "task_complete": "responding",
        "error": "responding",
    },
    "tool_executing": {
        "tool_complete": "responding",
        "tool_error": "responding",
    },
    "responding": {
        "turn_complete": "idle",
    },
    "concluding": {
        "report_done": "idle",  # Actually leads to END in graph
    },
}


# =============================================================================
# Pattern Definitions with Confidence Weights
# =============================================================================


@dataclass
class PatternConfig:
    """Configuration for a pattern match."""

    pattern: str
    confidence: float = CONFIDENCE_PATTERN_MATCH
    is_strong: bool = False  # Strong patterns indicate high confidence


# Pattern definitions with confidence weights
PATTERNS: dict[str, list[PatternConfig]] = {
    # End signals - high confidence when matched
    "end_signal": [
        PatternConfig(r"\bgoodbye\b", CONFIDENCE_EXACT_MATCH, is_strong=True),
        PatternConfig(
            r"\bthank\s+you\s+for\s+your\s+time\b", CONFIDENCE_EXACT_MATCH, is_strong=True
        ),
        PatternConfig(r"\bno\s+(more\s+)?questions\b", CONFIDENCE_EXACT_MATCH, is_strong=True),
        PatternConfig(r"\bthat\'s\s+all\b", 0.90, is_strong=True),
        PatternConfig(r"\bwrap\s*up\b", 0.75),  # Could be ambiguous
        PatternConfig(r"\bend\s+the\s+interview\b", CONFIDENCE_EXACT_MATCH, is_strong=True),
        PatternConfig(r"\bfinish\s+(up|the|this)\b", 0.70),
    ],
    # Profile-related requests (slow brain)
    "profile_request": [
        PatternConfig(
            r"\bgithub\s+(profile|account|repo)\b", CONFIDENCE_EXACT_MATCH, is_strong=True
        ),
        PatternConfig(r"\blinkedin\s+(profile|page)\b", CONFIDENCE_EXACT_MATCH, is_strong=True),
        PatternConfig(
            r"\b(check|look\s*at|review)\s+(my|the|their)\s+(github|linkedin)\b",
            0.95,
            is_strong=True,
        ),
        PatternConfig(r"\bresume\b", 0.85),
        PatternConfig(r"\bcv\b", 0.85),
        PatternConfig(r"\bverif(y|ication)\b", 0.70),  # Could be about something else
        PatternConfig(r"\bprofile\b", 0.50),  # Very ambiguous alone
    ],
    # Report requests (slow brain)
    "report_request": [
        PatternConfig(
            r"\b(generate|create|make)\s+(a\s+)?(final\s+)?report\b",
            CONFIDENCE_EXACT_MATCH,
            is_strong=True,
        ),
        PatternConfig(
            r"\bfinal\s+(report|evaluation|assessment)\b", CONFIDENCE_EXACT_MATCH, is_strong=True
        ),
        PatternConfig(r"\bevaluation\s+report\b", 0.95, is_strong=True),
        PatternConfig(r"\bsummary\s+report\b", 0.90),
        PatternConfig(r"\breport\b", 0.50),  # Too ambiguous alone
        PatternConfig(r"\bassessment\b", 0.50),
    ],
    # Deep analysis requests (slow brain)
    "deep_analysis": [
        PatternConfig(r"\bdeep\s*dive\b", 0.90, is_strong=True),
        PatternConfig(r"\bdetailed\s+(review|analysis)\b", 0.90, is_strong=True),
        PatternConfig(r"\banalyze\s+(in\s+depth|thoroughly)\b", 0.90, is_strong=True),
        PatternConfig(r"\b(comprehensive|thorough)\s+analysis\b", 0.90, is_strong=True),
        PatternConfig(r"\bcompare\s+and\s+contrast\b", 0.85),
        PatternConfig(r"\banalysis\b", 0.45),  # Too common, needs context
        PatternConfig(r"\banalyze\b", 0.45),
    ],
    # Search requests (fast brain with search tool)
    "search_request": [
        PatternConfig(r"\b(search|look\s*up|google)\s+(for\s+)?\b", 0.90, is_strong=True),
        PatternConfig(r"\bwhat\s+is\s+.{15,}\b", 0.75),  # Long "what is" questions
        PatternConfig(r"\blatest\s+(version|release|news)\b", 0.85),
        PatternConfig(r"\bhttps?://\S+\b", 0.95, is_strong=True),  # URLs
        PatternConfig(r"\bfind\s+(information|details)\s+about\b", 0.80),
    ],
    # Questions (fast brain)
    "question": [
        PatternConfig(r"\?$", 0.70),  # Ends with question mark
        PatternConfig(r"^(what|why|how|when|where|who|which)\s+", 0.65),
        PatternConfig(r"^(can|could|would|do|does|is|are)\s+", 0.55),
    ],
    # DSA: candidate submitting or discussing code (fast brain — DSA mode)
    "dsa_code_turn": [
        PatternConfig(r"\bdef\s+\w+\s*\(", 0.95, is_strong=True),   # Python function def
        PatternConfig(r"\bclass\s+\w+", 0.90, is_strong=True),       # Python class
        PatternConfig(r"\breturn\s+", 0.80),
        PatternConfig(r"\bfor\s+\w+\s+in\s+", 0.85, is_strong=True), # for loop
        PatternConfig(r"\bwhile\s+.+:", 0.85, is_strong=True),        # while loop
        PatternConfig(r"\bif\s+.+:", 0.70),
        PatternConfig(r"```", 0.90, is_strong=True),                   # code fence
    ],
    # DSA: candidate explaining complexity (fast brain — DSA mode)
    "dsa_complexity_turn": [
        PatternConfig(r"\bO\s*\(", 0.95, is_strong=True),             # Big-O notation
        PatternConfig(r"\btime\s+complexity\b", 0.90, is_strong=True),
        PatternConfig(r"\bspace\s+complexity\b", 0.90, is_strong=True),
        PatternConfig(r"\blinear\s+time\b", 0.85, is_strong=True),
        PatternConfig(r"\bquadratic\b", 0.85, is_strong=True),
        PatternConfig(r"\blogarithmic\b", 0.80),
        PatternConfig(r"\bconstant\s+space\b", 0.80),
    ],
}

# Tool suggestions for each classification
CLASSIFICATION_TOOLS: dict[str, list[str]] = {
    "end_signal": [],
    "profile_request": ["profile_crawler"],
    "report_request": ["report_descriptive", "report_data"],
    "deep_analysis": ["deep_analysis"],
    "search_request": ["tavily_search", "conversation"],
    "question": ["conversation"],
    "conversation": ["conversation"],
    "slow_task_trigger": [],  # No tools needed, just process pending tasks
    # DSA Round 2
    "dsa_code_turn": ["conversation"],       # Fast brain handles it
    "dsa_complexity_turn": ["conversation"], # Fast brain handles it
    "unknown": ["conversation"],
}

# Brain mapping for classifications
CLASSIFICATION_BRAIN: dict[str, Literal["fast", "slow", "end"]] = {
    "end_signal": "end",
    "profile_request": "slow",
    "report_request": "slow",
    "deep_analysis": "slow",
    "slow_task_trigger": "slow",  # Route to slow brain to process pending tasks
    "search_request": "fast",
    "question": "fast",
    "conversation": "fast",
    # DSA Round 2 — always fast brain (slow brain handles async evaluation tasks)
    "dsa_code_turn": "fast",
    "dsa_complexity_turn": "fast",
    "unknown": "fast",
}


# =============================================================================
# Pre-filter with Confidence Scoring
# =============================================================================


def run_prefilter(state: InterviewState) -> PrefilterResult:
    """Run the fast pre-filter with confidence scoring.

    This function uses regex pattern matching to quickly classify input
    and determine routing. It returns a confidence score that indicates
    how certain the classification is.

    Args:
        state: Current interview state

    Returns:
        PrefilterResult with classification, confidence, and suggestions
    """
    text = state.get("current_input", "").lower().strip()
    turn_count = state.get("turn_count", 0)
    max_turns = state.get("max_turns", 20)

    # Special case: Near end of interview, boost end signal confidence
    near_end = turn_count >= max_turns - 2

    best_match: tuple[str, float, list[str]] | None = None  # (classification, confidence, patterns)
    all_matches: list[tuple[str, float, str]] = []

    # Check each pattern category
    for classification, patterns in PATTERNS.items():
        matched_patterns: list[str] = []
        max_confidence = 0.0
        has_strong_match = False

        for pattern_config in patterns:
            if re.search(pattern_config.pattern, text):
                matched_patterns.append(pattern_config.pattern[:30])
                max_confidence = max(max_confidence, pattern_config.confidence)
                if pattern_config.is_strong:
                    has_strong_match = True

        if matched_patterns:
            # Boost confidence for multiple matches
            if len(matched_patterns) > 1:
                max_confidence = min(0.98, max_confidence + 0.05 * (len(matched_patterns) - 1))

            # Boost confidence for strong matches
            if has_strong_match:
                max_confidence = min(0.98, max_confidence + 0.05)

            # Context-based adjustments
            if classification == "end_signal" and near_end:
                max_confidence = min(0.98, max_confidence + 0.10)

            all_matches.append((classification, max_confidence, ", ".join(matched_patterns[:2])))

            if best_match is None or max_confidence > best_match[1]:
                best_match = (classification, max_confidence, matched_patterns)

    # Determine result
    if best_match is not None:
        classification_type = best_match[0]
        confidence = best_match[1]
        matched_patterns = best_match[2]

        # Check for conflicting high-confidence matches
        high_conf_matches = [m for m in all_matches if m[1] > 0.7 and m[0] != classification_type]
        if high_conf_matches:
            # Reduce confidence due to ambiguity
            confidence = min(confidence, 0.70)
            logger.debug(f"Reduced confidence due to conflicting matches: {high_conf_matches}")

    else:
        # Default to conversation with low confidence
        classification_type = "conversation"
        confidence = CONFIDENCE_DEFAULT
        matched_patterns = []

    # Get brain and tools for this classification
    brain = CLASSIFICATION_BRAIN.get(classification_type, "fast")
    tools = CLASSIFICATION_TOOLS.get(classification_type, ["conversation"])

    # Handle pending slow tasks
    if state.get("pending_slow_tasks"):
        brain = "slow"
        confidence = max(confidence, 0.90)  # High confidence when tasks are pending

    # Handle interview end conditions
    router = BrainRouter()
    if router.should_end_interview(state):
        brain = "end"
        classification_type = "end_signal"
        confidence = 0.95

    logger.debug(
        f"Prefilter: classification={classification_type}, "
        f"confidence={confidence:.2f}, brain={brain}, patterns={matched_patterns}"
    )

    return PrefilterResult(
        classification=classification_type,  # type: ignore
        confidence=confidence,
        matched_patterns=matched_patterns,
        suggested_brain=brain,
        suggested_tools=tools,
    )


def classify_input(
    text: str,
    context: dict[str, Any] | None = None,
) -> Literal[
    "conversation",
    "question",
    "profile_request",
    "report_request",
    "deep_analysis",
    "search_request",
    "end_signal",
    "unknown",
]:
    """Classify user input (legacy function for backward compatibility).

    For new code, use run_prefilter() which also returns confidence.

    Args:
        text: The user's input text
        context: Optional context (not used in new implementation)

    Returns:
        Classification type for routing
    """
    # Create minimal state for prefilter
    state: InterviewState = {"current_input": text}  # type: ignore
    result = run_prefilter(state)
    return result.classification


# =============================================================================
# Brain Router
# =============================================================================


class BrainRouter:
    """Manages DFA state and brain routing decisions.

    This class implements a deterministic finite automaton for routing
    interview messages to the appropriate brain (fast or slow).
    """

    def __init__(self, max_turns: int = 40):
        self.max_turns = max_turns

    def transition(
        self,
        current_state: DFAState,
        event: str,
    ) -> DFAState:
        """Execute a state transition.

        Args:
            current_state: Current DFA state
            event: The event triggering the transition

        Returns:
            New DFA state after transition
        """
        current = current_state["current_state"]

        if current not in TRANSITION_TABLE:
            logger.warning(f"Invalid DFA state: {current}")
            return current_state

        transitions = TRANSITION_TABLE[current]

        if event not in transitions:
            logger.warning(f"Invalid transition: {current} + {event}")
            return current_state

        new_state = transitions[event]
        existing_transitions = list(current_state.get("transitions", []))

        return DFAState(
            current_state=new_state,
            previous_state=current,
            transitions=existing_transitions + [f"{current}->{new_state}"],
            transition_count=current_state.get("transition_count", 0) + 1,
        )

    def should_end_interview(self, state: InterviewState) -> bool:
        """Check if interview should end based on deterministic rules."""
        # Rule 1: Max turns reached
        if state.get("turn_count", 0) >= state.get("max_turns", self.max_turns):
            return True

        # Rule 2: Interview already marked as ended
        if state.get("interview_ended", False):
            return True

        # A goodbye phrase alone doesn't end it: brain/interview_flow.py asks the
        # candidate to confirm, and sets interview_ended when the interview is over
        return False

    def has_pending_slow_tasks(self, state: InterviewState) -> bool:
        """Check if there are pending slow brain tasks."""
        pending = state.get("pending_slow_tasks", [])
        return len(pending) > 0

    def get_input_type(self, state: InterviewState) -> str:
        """Get the classification type for routing."""
        classification = state.get("input_classification", "unknown")
        return str(classification)


def route_to_brain(state: InterviewState) -> Literal["fast", "slow", "end"]:
    """Deterministic routing function for LangGraph conditional edges.

    This is the legacy routing function. For hybrid routing, use
    hybrid_route() from llm_router.py instead.

    Returns:
        "fast" - Route to fast brain (conversation)
        "slow" - Route to slow brain (analysis/reports)
        "end" - End the interview
    """
    router = BrainRouter()

    # Rule 1: Check for interview end
    if router.should_end_interview(state):
        logger.info("Routing to END: interview end conditions met")
        return "end"

    # Rule 2: Check for pending slow tasks (priority queue)
    if router.has_pending_slow_tasks(state):
        logger.info("Routing to SLOW brain: pending slow tasks in queue")
        return "slow"

    # Rule 3: Route based on input classification
    input_type = router.get_input_type(state)

    slow_types = {"profile_request", "report_request", "deep_analysis", "slow_task_trigger"}
    if input_type in slow_types:
        logger.info(f"Routing to SLOW brain: input type is '{input_type}'")
        return "slow"

    # Default: fast brain for conversation
    logger.info(f"Routing to FAST brain: input type is '{input_type}'")
    return "fast"


async def hybrid_route_to_brain(state: InterviewState) -> Literal["fast", "slow", "end"]:
    """Hybrid routing function using pre-filter + LLM.

    This is the main routing function for LangGraph conditional edges
    when using hybrid routing.

    Returns:
        "fast" - Route to fast brain (conversation)
        "slow" - Route to slow brain (analysis/reports)
        "end" - End the interview
    """
    from brain.brains.llm_router import hybrid_route

    decision = await hybrid_route(state, confidence_threshold=PREFILTER_CONFIDENCE_THRESHOLD)
    return decision.brain


# =============================================================================
# Graph Node Functions
# =============================================================================


async def input_processor_node(state: InterviewState) -> dict[str, Any]:
    """Process and classify input before routing.

    This node:
    1. Merges background verification results from Redis
    2. Checks for prompt injection attacks (SECURITY LAYER 1)
    3. Runs the pre-filter for fast classification
    4. Invokes LLM router if confidence is low
    5. Updates DFA state
    6. Manages message window (keeps last 10)
    """
    from brain.brains.llm_router import hybrid_route
    from brain.services.background_verifier import get_pending_verification_results
    from core.prompt_injection import detect_injection

    # Track state updates to merge at the end
    state_updates: dict[str, Any] = {}

    # =========================================================================
    # Merge background verification results from Redis
    # =========================================================================
    session_id = state.get("session_id")
    if session_id:
        bg_results = await get_pending_verification_results(session_id)
        if bg_results:
            bg_claim_count = bg_results.get("claim_count", 0)
            logger.info(
                f"[INPUT_PROCESSOR] Merging {bg_claim_count} background verification results"
            )

            # Import trust score calculator
            from brain.brains.slow_brain import _calculate_trust_score

            # Merge verified claims
            existing_verified = list(state.get("verified_claims", []))
            new_verified = bg_results.get("verified_claims", [])
            merged_verified = existing_verified + new_verified

            # Recalculate trust score with all verified claims
            merged_trust = _calculate_trust_score(merged_verified)

            # Remove verified claims from pending list
            verified_ids = {v.get("claim", {}).get("id") for v in new_verified if v.get("claim")}
            remaining_pending = [
                c for c in state.get("pending_claims", []) if c.get("id") not in verified_ids
            ]

            # Store updates for later
            state_updates["verified_claims"] = merged_verified
            state_updates["trust_score"] = merged_trust
            state_updates["pending_claims"] = remaining_pending

            logger.info(
                f"[INPUT_PROCESSOR] Merged verification: "
                f"verified={len(merged_verified)}, pending={len(remaining_pending)}, "
                f"trust_score={merged_trust:.2f}"
            )

    # SECURITY LAYER 1: Check for prompt injection attacks
    current_input = state.get("current_input", "")
    if current_input:
        detection = detect_injection(current_input)

        if detection.is_malicious:
            logger.warning(
                f"[SECURITY] Prompt injection blocked: "
                f"threat_level={detection.threat_level}, "
                f"confidence={detection.confidence:.2f}, "
                f"reason={detection.reason}"
            )

            # Log security event (will be stored by security monitor)
            security_event = {
                "session_id": state.get("session_id"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "threat_level": detection.threat_level,
                "confidence": detection.confidence,
                "reason": detection.reason,
                "original_input": current_input[:200],  # Truncate for storage
            }

            # Store in state for security monitoring
            security_events = list(state.get("security_events", []))
            security_events.append(security_event)

            # For high/critical threats, use sanitized text or reject completely
            if detection.threat_level in ["high", "critical"]:
                logger.error(
                    f"[SECURITY] {detection.threat_level.upper()} threat detected - "
                    f"using sanitized input"
                )
                # Update state with sanitized input
                state = {**state, "current_input": detection.sanitized_text}
                current_input = detection.sanitized_text
            else:
                # Medium/low threats: log and continue with sanitized text
                logger.info(
                    f"[SECURITY] {detection.threat_level} threat detected - "
                    f"proceeding with sanitized input"
                )
                state = {**state, "current_input": detection.sanitized_text}
                current_input = detection.sanitized_text

    # Run pre-filter first
    prefilter_result = run_prefilter(state)

    # Force profile request if not started but URLs exist
    if (
        state.get("profile_status") == "not_started"
        and state.get("candidate_urls")
        and not state.get("candidate_profile")
    ):
        logger.info("[INPUT_PROCESSOR] Auto-detecting profile crawl request")
        prefilter_result = PrefilterResult(
            classification="profile_request",
            confidence=1.0,
            matched_patterns=["auto_init"],
            suggested_brain="slow",
            suggested_tools=["profile_crawler"],
        )

    # Decide if we need LLM routing
    if prefilter_result.confidence >= PREFILTER_CONFIDENCE_THRESHOLD:
        # Use pre-filter result directly
        routing_decision = RoutingDecision(
            brain=prefilter_result.suggested_brain,
            confidence=prefilter_result.confidence,
            reasoning=f"Prefilter: matched {prefilter_result.classification}",
            routing_method="prefilter",
            suggested_tools=prefilter_result.suggested_tools,
            tool_params={},
            input_classification=prefilter_result.classification,
        )
        logger.info(
            f"[INPUT_PROCESSOR] Using prefilter (confidence={prefilter_result.confidence:.2f}): "
            f"brain={routing_decision.brain}"
        )
    else:
        # Use LLM router for better accuracy
        routing_decision = await hybrid_route(state, prefilter_result)
        logger.info(
            f"[INPUT_PROCESSOR] Using LLM router "
            f"(prefilter confidence={prefilter_result.confidence:.2f}): "
            f"brain={routing_decision.brain}, confidence={routing_decision.confidence:.2f}"
        )

    # Transition DFA state
    dfa = state.get(
        "dfa",
        {
            "current_state": "idle",
            "previous_state": None,
            "transitions": [],
            "transition_count": 0,
        },
    )

    router = BrainRouter()
    new_dfa = router.transition(dfa, "user_input")

    # Manage message window (keep last 10)
    messages = list(state.get("messages", []))
    if len(messages) > 10:
        old_messages = messages[:-10]
        messages = messages[-10:]

        # Create summary of old messages
        key_points = []
        for msg in old_messages:
            content = msg.get("content", "")[:100]
            if msg.get("role") == "user":
                key_points.append(content)

        summary = {
            "turn_range": (0, len(old_messages)),
            "key_points": key_points[:5],
            "topics_discussed": [],
            "summary_text": f"Previous {len(old_messages)} messages summarized.",
        }
    else:
        summary = state.get("message_summary")

    # Collect security events from earlier processing
    security_events = state.get("security_events", [])

    # An explicit end (e.g. end_call message) must not be reclassified from the
    # empty input as ordinary conversation.
    input_classification = (
        "end_signal" if state.get("interview_ended") else routing_decision.input_classification
    )

    # Build final return dict, merging background verification results
    result = {
        "input_classification": input_classification,
        "routing_confidence": routing_decision.confidence,
        "routing_method": routing_decision.routing_method,
        "routing_reasoning": routing_decision.reasoning,
        "suggested_tools": routing_decision.suggested_tools,
        "suggested_tool_params": routing_decision.tool_params,
        "dfa": new_dfa,
        "messages": messages,
        "message_summary": summary,
        "security_events": security_events,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }

    # Merge any background verification state updates
    result.update(state_updates)

    return result


async def brain_router_node(state: InterviewState) -> dict[str, Any]:
    """Update brain mode based on routing decision.

    This node is called after the conditional edge has been evaluated
    to update the state with the routing decision.
    """
    dfa = state.get(
        "dfa",
        {
            "current_state": "routing",
            "previous_state": None,
            "transitions": [],
            "transition_count": 0,
        },
    )

    router = BrainRouter()

    # Use the routing decision from input_processor
    input_type = state.get("input_classification", "conversation")

    if router.should_end_interview(state):
        event = "is_end_signal"
        brain_mode: Literal["fast", "slow", "idle"] = "idle"
    elif input_type in {"profile_request", "report_request", "deep_analysis"}:
        event = "is_task"
        brain_mode = "slow"
    else:
        event = "is_conversation"
        brain_mode = "fast"

    new_dfa = router.transition(dfa, event)

    return {
        "dfa": new_dfa,
        "brain_mode": brain_mode,
    }
