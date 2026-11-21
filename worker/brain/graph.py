"""Dual-Brain LangGraph Interview Agent with Hybrid Routing.

Main graph assembly that implements:
- Hybrid routing: Fast pre-filter + LLM router for accuracy
- Fast brain for low-latency conversation
- Slow brain for deep analysis and reports
- Horizontal/vertical scalability through LLM sharding

Architecture:
    START -> input_processor -> brain_router -> [fast|slow|end] -> response_finalizer -> END

The input_processor now uses hybrid routing:
1. Fast regex pre-filter with confidence scoring
2. LLM router (Gemini Flash) for ambiguous cases
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Literal

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from brain.brains.fast_brain import fast_brain_node
from brain.brains.router import (
    BrainRouter,
    brain_router_node,
    input_processor_node,
)
from brain.brains.slow_brain import slow_brain_node
from brain.interview_flow import closing_message
from brain.services.reply_publisher import publish_reply_early
from brain.state import InterviewState, create_default_dfa_state
from brain.tools.slow.report_generator import (
    generate_analytics_report,
    generate_descriptive_report,
)
from scoring.integration import (
    scoring_finalize_node,
    scoring_process_exchange_node,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Graph Nodes
# =============================================================================


async def response_finalizer_node(state: InterviewState) -> dict[str, Any]:
    """Finalize the response before returning.

    This node:
    1. Formats the response
    2. Updates final state
    3. Prepares for next turn
    """
    session_id = state.get("session_id", "unknown")
    routing_method = state.get("routing_method", "unknown")
    routing_confidence = state.get("routing_confidence", 0.0)

    logger.info(
        f"[FINALIZER] Session {session_id}: Finalizing response "
        f"(routing: {routing_method}, confidence: {routing_confidence:.2f})"
    )

    # Update DFA to idle state for next turn
    dfa = state.get("dfa", create_default_dfa_state())
    dfa = dict(dfa)
    dfa["previous_state"] = dfa.get("current_state")
    dfa["current_state"] = "idle"
    raw_transitions = dfa.get("transitions")
    existing_transitions: list[str] = raw_transitions if isinstance(raw_transitions, list) else []
    transitions = existing_transitions + ["finalizer->idle"]
    dfa["transitions"] = transitions

    # Clear current input and routing state for next turn
    return {
        "dfa": dfa,
        "current_input": "",
        "brain_mode": "idle",
        "suggested_tools": [],  # Clear tool suggestions
        "suggested_tool_params": {},
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


async def conclude_interview_node(state: InterviewState) -> dict[str, Any]:
    """End the session: say goodbye first, then write the session report."""
    session_id = state.get("session_id", "unknown")
    logger.info(f"[CONCLUDE] Session {session_id}: Concluding session")

    # Goodbye in the session's language (brain/interview_flow.py). Spoken before
    # the report is written, so the learner isn't left waiting on it.
    end_reason = state.get("end_reason") or "completed"
    response = closing_message(end_reason, state.get("language"))
    if state.get("session_mode") == "talk" and end_reason in ("completed", "candidate_ended", "user_ended", "time_limit", "turn_limit"):
        from brain.talk import TALK_GOODBYES

        response = TALK_GOODBYES.get(str(state.get("language")), TALK_GOODBYES["en-IN"])
    await publish_reply_early(response)

    report_status: Literal["not_started", "pending", "in_progress", "completed", "failed"] = "in_progress"
    descriptive_report = None
    analytics_data = None
    try:
        desc_result = await generate_descriptive_report(state)
        if desc_result.success:
            descriptive_report = desc_result.data
        analytics_result = await generate_analytics_report(state)
        if analytics_result.success:
            analytics_data = analytics_result.data
        # "failed": retried by the worker's sweep
        report_status = "completed" if descriptive_report else "failed"
    except Exception as e:
        logger.error(f"[CONCLUDE] Report generation failed: {e}")
        report_status = "failed"

    dfa = dict(state.get("dfa", create_default_dfa_state()))
    dfa["current_state"] = "concluding"

    return {
        "interview_ended": True,
        "end_reason": end_reason,
        "report_status": report_status,
        "descriptive_report": descriptive_report,
        "analytics_data": analytics_data,
        "response": response,
        "dfa": dfa,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


UNDERSTANDING_TIMEOUT_S = 8.0


async def scoring_process_node(state: InterviewState) -> dict[str, Any]:
    """After the reply was spoken: update what the learner understands.

    (The old skill-tree scoring still runs if a tree was set up, which no
    longer happens for study sessions.)
    """
    try:
        # Bounded: the session lock is held meanwhile, and the next turn waits on it
        updates = await asyncio.wait_for(update_understanding(state), timeout=UNDERSTANDING_TIMEOUT_S)
    except Exception as e:
        logger.error(f"[UNDERSTANDING] update skipped: {type(e).__name__}: {e}")
        updates = {}
    skill_tree_state = state.get("skill_tree")
    if not skill_tree_state or not skill_tree_state.get("tree_initialized"):
        return updates

    # System inputs ([NO ANSWER], [CANDIDATE RETURNED], ...) are not answers to score
    if str(state.get("current_input") or "").startswith("["):
        return {}

    try:
        return await scoring_process_exchange_node(state)
    except Exception as e:
        logger.error(f"[SCORING] Error in scoring process node: {e}")
        return {}


async def update_understanding(state: InterviewState) -> dict[str, Any]:
    """The gentle evaluator's bookkeeping, after the reply (brain/understanding.py).

    - a new topic was explained: list its key ideas (the understanding map)
    - the learner answered a check: assess the answer against the open ideas
    - the buddy asked a check question: remember which idea it was about
    """
    from brain import understanding as u_mod

    if str(state.get("current_input") or "").startswith("[") or state.get("session_mode") == "talk":
        return {}
    u = dict(state.get("understanding") or {})
    topic = str(state.get("current_topic") or "")
    language = str(state.get("language") or "en-IN")
    classification = state.get("input_classification")

    # A topic we have no map for yet (explained, or the learner asked to be quizzed)
    if (
        classification in ("explain_request", "quiz_request")
        and topic
        and topic != "not chosen yet"
        and topic.lower() != str(u.get("topic") or "").lower()
    ):
        points = await u_mod.plan_points(topic, language)
        if points:
            u = u_mod.new_map(topic, language, points)
            logger.info(f"[UNDERSTANDING] {topic}: {len(points)} key ideas")

    # The learner answered the buddy's question about an idea
    if state.get("answering_check") and u.get("points"):
        messages = state.get("messages") or []
        asked = next((m.get("content", "") for m in reversed(messages[:-2]) if m.get("role") == "assistant"), "")
        results = await u_mod.assess(asked, str(state.get("current_input") or ""), u["points"])
        u = u_mod.apply_assessment(u, results)
        logger.info(f"[UNDERSTANDING] assessed: {results}")

    # The buddy asked a check question this turn (a quiz, or a follow-up/coaching
    # question about an idea still open)
    target = state.get("check_target") or ""
    if not target and classification == "quiz_request":
        first = u_mod.next_point({**state, "understanding": u})
        target = first["id"] if first else ""
    if target and (classification == "quiz_request" or state.get("answering_check")):
        open_ids = {p["id"] for p in u.get("points") or [] if p["status"] != "understood"}
        if u.get("awaiting") in open_ids:
            u = u_mod.asked_about(u, u["awaiting"])  # still on the same idea
        elif target in open_ids:
            u = u_mod.asked_about(u, target)
        elif "?" in str(state.get("response") or ""):
            # They got it, and the buddy moved on with a question about the next idea
            nxt = u_mod.next_point({**state, "understanding": u})
            if nxt:
                u = u_mod.asked_about(u, nxt["id"])

    return {"understanding": u} if u != (state.get("understanding") or {}) else {}


async def scoring_finalize_and_compare_node(state: InterviewState) -> dict[str, Any]:
    """Finalize the skill-tree scores at the end of the session."""
    skill_tree_state = state.get("skill_tree")
    if not skill_tree_state or not skill_tree_state.get("tree_initialized"):
        return {}
    try:
        return await scoring_finalize_node(state)
    except Exception as e:
        logger.error(f"[SCORING] Error in scoring finalize node: {e}")
        return {}


# =============================================================================
# Routing Functions
# =============================================================================


def brain_route_decision(state: InterviewState) -> Literal["fast", "slow", "end"]:
    """Routing decision for conditional edges.

    This function uses the routing decision made by input_processor_node,
    which already applied hybrid routing (pre-filter + LLM).
    """
    router = BrainRouter()

    # Check for interview end conditions first
    if router.should_end_interview(state):
        logger.info("Routing to END: interview end conditions met")
        return "end"

    # Check for pending slow tasks
    if router.has_pending_slow_tasks(state):
        logger.info("Routing to SLOW brain: pending slow tasks in queue")
        return "slow"

    # Use the classification from hybrid routing
    input_type = state.get("input_classification", "conversation")
    routing_method = state.get("routing_method", "prefilter")
    routing_confidence = state.get("routing_confidence", 0.0)

    slow_types = {"report_request", "deep_analysis"}

    if input_type in slow_types:
        logger.info(
            f"Routing to SLOW brain: input type is '{input_type}' "
            f"(method={routing_method}, confidence={routing_confidence:.2f})"
        )
        return "slow"

    logger.info(
        f"Routing to FAST brain: input type is '{input_type}' "
        f"(method={routing_method}, confidence={routing_confidence:.2f})"
    )
    return "fast"


# =============================================================================
# Main Graph Construction
# =============================================================================


def create_dual_brain_graph(
    checkpointer: Any | None = None,
    use_memory_saver: bool = True,
) -> Any:
    """Create the main dual-brain interview graph with hybrid routing.

    Architecture:
    ```
    START
      |
      v
    input_processor (hybrid routing: pre-filter + LLM)
      |
      v
    brain_router (uses routing decision from input_processor)
      |
      +--[fast]---> fast_brain ----+
      |                            |
      +--[slow]---> slow_brain ----+
      |                            |
      +--[end]----> conclude ------+
                                   |
                                   v
                           response_finalizer
                                   |
                                   v
                                  END
    ```

    Routing Strategy:
    - Pre-filter runs first (~10ms) with confidence scoring
    - If confidence >= 0.85, use pre-filter decision directly
    - If confidence < 0.85, invoke LLM router (~200ms) for better accuracy

    Args:
        checkpointer: LangGraph checkpointer for state persistence.
                     Use RedisSaver for production, MemorySaver for testing.
        use_memory_saver: If True and no checkpointer provided, use MemorySaver

    Returns:
        Compiled StateGraph ready for invocation
    """
    # Create the graph with our state schema
    graph = StateGraph(InterviewState)

    # =========================================================================
    # Add Nodes
    # =========================================================================

    # Entry nodes (input_processor now includes hybrid routing)
    graph.add_node("input_processor", input_processor_node)
    graph.add_node("brain_router", brain_router_node)

    # Brain nodes
    graph.add_node("fast_brain", fast_brain_node)
    graph.add_node("slow_brain", slow_brain_node)

    # Scoring node (processes Q&A exchanges for skill tree)
    graph.add_node("scoring_process", scoring_process_node)

    # Exit nodes
    graph.add_node("conclude", conclude_interview_node)
    graph.add_node("scoring_finalize", scoring_finalize_and_compare_node)
    graph.add_node("response_finalizer", response_finalizer_node)

    # =========================================================================
    # Add Edges
    # =========================================================================

    # Entry flow
    graph.add_edge(START, "input_processor")
    graph.add_edge("input_processor", "brain_router")

    # Conditional routing based on hybrid routing decision
    graph.add_conditional_edges(
        "brain_router",
        brain_route_decision,
        {
            "fast": "fast_brain",
            "slow": "slow_brain",
            "end": "conclude",
        },
    )

    # Brain outputs go through scoring process, then to finalizer
    graph.add_edge("fast_brain", "scoring_process")
    graph.add_edge("slow_brain", "scoring_process")
    graph.add_edge("scoring_process", "response_finalizer")

    # Conclude goes through scoring finalize before finalizer
    graph.add_edge("conclude", "scoring_finalize")
    graph.add_edge("scoring_finalize", "response_finalizer")

    # Finalizer to END
    graph.add_edge("response_finalizer", END)

    # =========================================================================
    # Compile
    # =========================================================================

    # Use provided checkpointer or default to MemorySaver
    if checkpointer is None and use_memory_saver:
        checkpointer = MemorySaver()

    compiled = graph.compile(checkpointer=checkpointer)

    logger.info(
        "Dual-brain interview graph created with hybrid routing: "
        "input_processor (hybrid) -> brain_router -> [fast|slow|conclude] -> response_finalizer"
    )

    return compiled


# =============================================================================
# Convenience Functions
# =============================================================================


def create_interview_graph(
    checkpointer: Any | None = None,
    use_memory_saver: bool = True,
) -> Any:
    """Alias for create_dual_brain_graph for backward compatibility.

    This is the main entry point for creating the interview graph.
    """
    return create_dual_brain_graph(checkpointer, use_memory_saver)


async def process_message(
    graph: Any,
    session_id: str,
    message: str,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Process a single message through the dual-brain graph.

    Convenience function for invoking the graph with proper configuration.

    Args:
        graph: Compiled StateGraph
        session_id: Session identifier
        message: User message to process
        config: Optional LangGraph configuration

    Returns:
        Updated state with response
    """
    if config is None:
        config = {"configurable": {"thread_id": session_id}}

    # Build initial state update
    state_update = {
        "session_id": session_id,
        "current_input": message,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }

    # Invoke the graph
    result = await graph.ainvoke(state_update, config=config)

    return result


# =============================================================================
# Graph Visualization (for debugging)
# =============================================================================


def get_graph_diagram() -> str:
    """Return ASCII diagram of the dual-brain graph structure with hybrid routing."""
    return """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │              DUAL-BRAIN INTERVIEW GRAPH (HYBRID ROUTING)                 │
    ├─────────────────────────────────────────────────────────────────────────┤
    │                                                                          │
    │                              START                                       │
    │                                │                                         │
    │                                ▼                                         │
    │                     ┌─────────────────────┐                              │
    │                     │   input_processor   │ ← Hybrid routing:            │
    │                     │                     │   1. Fast pre-filter (~10ms) │
    │                     │                     │   2. LLM router if needed    │
    │                     └──────────┬──────────┘      (~200ms)                │
    │                                │                                         │
    │                                ▼                                         │
    │                     ┌─────────────────────┐                              │
    │                     │    brain_router     │ ← Uses routing decision      │
    │                     └──────────┬──────────┘   from input_processor       │
    │                                │                                         │
    │              ┌─────────────────┼─────────────────┐                       │
    │              │                 │                 │                       │
    │              ▼                 ▼                 ▼                       │
    │     ┌────────────────┐ ┌────────────────┐ ┌────────────────┐            │
    │     │   fast_brain   │ │   slow_brain   │ │    conclude    │            │
    │     │ (Gemini Flash) │ │ (Gemini Pro)   │ │  (Reports)     │            │
    │     │                │ │                │ │                │            │
    │     │ Tools:         │ │ Tools:         │ │                │            │
    │     │ - conversation │ │ - profile_crawl│ │                │            │
    │     │ - tavily_search│ │ - reports      │ │                │            │
    │     │ - timestamp    │ │ - deep_analysis│ │                │            │
    │     └───────┬────────┘ └───────┬────────┘ └───────┬────────┘            │
    │             │                  │                  │                      │
    │             └──────────────────┼──────────────────┘                      │
    │                                │                                         │
    │                                ▼                                         │
    │                     ┌─────────────────────┐                              │
    │                     │ response_finalizer  │ ← Format & prepare           │
    │                     └──────────┬──────────┘                              │
    │                                │                                         │
    │                                ▼                                         │
    │                               END                                        │
    │                                                                          │
    └─────────────────────────────────────────────────────────────────────────┘

    Hybrid Routing Strategy:
    ┌─────────────────────────────────────────────────────────────────────────┐
    │  User Input → Pre-filter (regex) → Confidence Check                     │
    │                                          │                              │
    │                    ┌─────────────────────┴─────────────────────┐        │
    │                    │                                           │        │
    │              Confidence >= 0.85                         Confidence < 0.85│
    │                    │                                           │        │
    │                    ▼                                           ▼        │
    │            Use Pre-filter                              Use LLM Router   │
    │            Decision (~10ms)                            (~200ms)         │
    └─────────────────────────────────────────────────────────────────────────┘
    """


# =============================================================================
# Routing Statistics
# =============================================================================


def get_routing_stats() -> dict[str, Any]:
    """Get routing statistics from the LLM router cache."""
    from brain.brains.llm_router import get_routing_stats as get_llm_stats

    return get_llm_stats()


def clear_routing_cache() -> None:
    """Clear the LLM router cache."""
    from brain.brains.llm_router import clear_routing_cache as clear_llm_cache

    clear_llm_cache()


# =============================================================================
# Legacy Functions (for backward compatibility)
# =============================================================================


def create_interview_graph_with_conditionals(
    checkpointer: Any | None = None,
) -> Any:
    """Legacy function - redirects to dual-brain graph.

    Maintained for backward compatibility with existing code.
    """
    logger.warning(
        "create_interview_graph_with_conditionals is deprecated. "
        "Use create_dual_brain_graph instead."
    )
    return create_dual_brain_graph(checkpointer)
