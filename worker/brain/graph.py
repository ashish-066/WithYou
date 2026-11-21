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
    """Conclude the interview and generate final reports.

    This node:
    1. Processes any remaining pending claims
    2. Calculates final trust score
    3. Marks interview as ended
    4. Triggers report generation
    5. Prepares final response
    """
    from brain.brains.slow_brain import _calculate_trust_score, _verify_single_claim
    from brain.state import VerificationResult

    session_id = state.get("session_id", "unknown")
    logger.info(f"[CONCLUDE] Session {session_id}: Concluding interview")

    # Process any remaining pending claims before generating reports
    pending_claims = state.get("pending_claims", [])
    verified_claims = list(state.get("verified_claims", []))
    candidate_profile = state.get("candidate_profile")

    if pending_claims:
        logger.info(
            f"[CONCLUDE] Session {session_id}: Processing {len(pending_claims)} "
            "remaining pending claims"
        )
        for claim in pending_claims:
            if candidate_profile:
                result = await _verify_single_claim(claim, candidate_profile)
            else:
                # No profile data - mark as unverified (no trust penalty)
                result = VerificationResult(
                    claim=claim,
                    evidence=[],
                    verdict="unverified",
                    confidence=0.0,
                    reasoning="No candidate profile data available for verification",
                    suggested_followup=None,
                )
            verified_claims.append(result)

    # Calculate final trust score
    trust_score = _calculate_trust_score(verified_claims)

    # Create updated state for report generation
    # This ensures reports use the final claim verification data
    updated_state = dict(state)
    updated_state["pending_claims"] = []
    updated_state["verified_claims"] = verified_claims
    updated_state["trust_score"] = trust_score

    # Generate reports
    report_status: Literal["not_started", "pending", "in_progress", "completed", "failed"] = "in_progress"
    descriptive_report = None
    analytics_data = None

    try:
        # Generate descriptive report with updated state
        desc_result = await generate_descriptive_report(updated_state)
        if desc_result.success:
            descriptive_report = desc_result.data

        # Generate analytics report with updated state
        analytics_result = await generate_analytics_report(updated_state)
        if analytics_result.success:
            analytics_data = analytics_result.data

        # "failed": retried by the worker's sweep, and from the report page
        report_status = "completed" if descriptive_report else "failed"
    except Exception as e:
        logger.error(f"[CONCLUDE] Report generation failed: {e}")
        report_status = "failed"

    # Closing words match how the interview ended (brain/interview_flow.py)
    end_reason = state.get("end_reason") or "completed"
    response = closing_message(end_reason)

    # Update DFA to concluding state
    dfa = state.get("dfa", create_default_dfa_state())
    dfa = dict(dfa)
    dfa["current_state"] = "concluding"

    return {
        "interview_ended": True,
        "end_reason": end_reason,
        "report_status": report_status,
        "descriptive_report": descriptive_report,
        "analytics_data": analytics_data,
        "response": response,
        "dfa": dfa,
        "pending_claims": [],
        "verified_claims": verified_claims,
        "trust_score": trust_score,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


async def scoring_process_node(state: InterviewState) -> dict[str, Any]:
    """Process Q&A exchange for skill tree scoring.

    This node extracts evidence from the latest exchange and updates
    the skill tree. Only runs if skill tree is initialized.
    """
    skill_tree_state = state.get("skill_tree")
    if not skill_tree_state or not skill_tree_state.get("tree_initialized"):
        # Skill tree not initialized, skip scoring
        return {}

    # System inputs ([NO ANSWER], [CANDIDATE RETURNED], ...) are not answers to score
    if str(state.get("current_input") or "").startswith("["):
        return {}

    try:
        return await scoring_process_exchange_node(state)
    except Exception as e:
        logger.error(f"[SCORING] Error in scoring process node: {e}")
        return {}


async def scoring_finalize_and_compare_node(state: InterviewState) -> dict[str, Any]:
    """Finalize scoring and run ELO comparison at interview end.

    This node:
    1. Calculates final weighted scores
    2. Compares against existing candidate pool
    3. Updates ELO ratings
    """
    skill_tree_state = state.get("skill_tree")
    if not skill_tree_state or not skill_tree_state.get("tree_initialized"):
        return {}

    try:
        # Calculate final score and update ELO
        result = await scoring_finalize_node(state)

        # Store weighted score for future comparisons
        if result.get("skill_tree"):
            from core.redis import get_redis_client

            session_id = state.get("session_id", "")
            candidate_id = state.get("candidate_id") or session_id
            role_id = skill_tree_state.get("role_id", "")

            try:
                redis = await get_redis_client()
                from scoring.elo_system import EloSystem
                from scoring.models import RoleRequirements, SkillRequirement
                from scoring.score_calculator import ScoreCalculator
                from scoring.tree_manager import SkillTreeManager

                # Get the skill tree
                tree_manager = SkillTreeManager(redis)
                tree = await tree_manager.get_tree(session_id)

                if tree:
                    # Build requirements
                    skill_weights = skill_tree_state.get("skill_weights", {})
                    requirements = RoleRequirements(
                        title=skill_tree_state.get("role_title", ""),
                        skills=[
                            SkillRequirement(skill_name=name, weight=weight)
                            for name, weight in skill_weights.items()
                        ],
                    )

                    # Calculate score
                    score_calculator = ScoreCalculator()
                    weighted_score = score_calculator.calculate_score(tree, requirements)

                    # Store weighted score for comparisons

                    score_key = f"weighted_score:{role_id}:{candidate_id}"
                    await redis.set(score_key, weighted_score.model_dump_json())

                    # Initialize ELO system and compare against pool
                    elo_system = EloSystem(redis, score_calculator)

                    # Get existing candidates
                    role_candidates_key = f"role_candidates:{role_id}"
                    existing_ids = await redis.smembers(role_candidates_key)

                    if existing_ids:
                        # Compare against existing candidates
                        for existing_id in existing_ids:
                            if isinstance(existing_id, bytes):
                                existing_id = existing_id.decode()
                            if existing_id == candidate_id:
                                continue

                            # Get existing candidate's score
                            existing_score_key = f"weighted_score:{role_id}:{existing_id}"
                            existing_score_data = await redis.get(existing_score_key)

                            if existing_score_data:
                                from scoring.models import WeightedScore

                                if isinstance(existing_score_data, bytes):
                                    existing_score_data = existing_score_data.decode()
                                existing_score = WeightedScore.model_validate_json(
                                    existing_score_data
                                )

                                # Record match
                                await elo_system.record_match(
                                    weighted_score, existing_score, requirements
                                )

                    # Save new candidate's rating
                    rating = await elo_system.get_rating(candidate_id, role_id)
                    await elo_system.save_rating(rating)

                    # Update skill tree state with ELO data
                    updated_skill_tree = dict(result.get("skill_tree", skill_tree_state))
                    updated_skill_tree["elo_rating"] = rating.rating

                    # Calculate percentile
                    rankings = await elo_system.get_role_rankings(role_id)
                    if rankings:
                        all_ratings = [r.rating for r in rankings]
                        from scoring.elo_system import calculate_percentile

                        updated_skill_tree["elo_percentile"] = calculate_percentile(
                            rating.rating, all_ratings
                        )

                    result["skill_tree"] = updated_skill_tree

                await redis.aclose()
            except Exception as e:
                logger.error(f"[SCORING] Error in ELO comparison: {e}")

        return result
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

    # DSA Round 2: every candidate turn is handled by the fast brain's DSA tool.
    # (Profile/report classifiers misfire on technical talk.)
    if state.get("interview_mode") == "round2_dsa":
        logger.info("Routing to FAST brain: DSA round")
        return "fast"

    # Check for pending slow tasks
    if router.has_pending_slow_tasks(state):
        logger.info("Routing to SLOW brain: pending slow tasks in queue")
        return "slow"

    # Use the classification from hybrid routing
    input_type = state.get("input_classification", "conversation")
    routing_method = state.get("routing_method", "prefilter")
    routing_confidence = state.get("routing_confidence", 0.0)

    slow_types = {"profile_request", "report_request", "deep_analysis"}

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
