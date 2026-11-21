"""Fast Brain subgraph for conversation handling.

Low-latency processing for interview dialogue using Gemini Flash.
Handles:
- Understanding candidate responses
- Generating interviewer responses
- Quick tool execution (search, timestamps)
- Claim detection for verification queue
- Real-time response scoring

Now supports hybrid routing: consumes tool suggestions from LLM router.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from langgraph.graph import END, StateGraph

from brain.candidate_background import profile_for_checks
from brain.services.reply_publisher import publish_reply_early
from brain.state import (
    Claim,
    InterviewState,
    Message,
    TimestampNote,
    ToolCall,
    ToolResult,
)
from brain.tools.fast.conversation import conversation_tool
from brain.tools.fast.response_scorer import score_response
from brain.tools.fast.tavily_search import tavily_search_tool
from brain.tools.fast.timestamp_noter import timestamp_noter_tool
from brain.tools.fast.tool_decider import tool_decider

logger = logging.getLogger(__name__)


def _calculate_video_seconds(state: InterviewState, timestamp: str) -> float | None:
    """Calculate elapsed seconds from interview start for video synchronization.

    Args:
        state: The interview state containing started_at timestamp
        timestamp: The current timestamp in ISO format

    Returns:
        Elapsed seconds from interview start, or None if calculation fails
    """
    try:
        started_at = state.get("started_at")
        if not started_at:
            return None

        # Parse timestamps
        start_time = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        current_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

        # Calculate difference in seconds
        delta = (current_time - start_time).total_seconds()
        return max(0.0, delta)  # Ensure non-negative
    except Exception:
        return None


# =============================================================================
# Fast Brain Nodes
# =============================================================================


async def understand_node(state: InterviewState) -> dict[str, Any]:
    """Understand and parse the candidate's response.

    This node:
    1. Processes the user input
    2. Checks for LLM router tool suggestions (hybrid routing)
    3. Falls back to regex-based tool decider if no suggestions
    4. Updates conversation context
    """
    current_input = state.get("current_input", "")
    session_id = state.get("session_id", "unknown")
    routing_method = state.get("routing_method", "prefilter")

    logger.info(
        f"[FAST/UNDERSTAND] Session {session_id}: {current_input[:50]}... "
        f"(routing: {routing_method})"
    )

    # Build tool queue - prefer LLM router suggestions when available
    tool_queue: list[ToolCall] = []
    suggested_tools = state.get("suggested_tools", [])
    suggested_params = state.get("suggested_tool_params", {})

    if suggested_tools and routing_method == "llm":
        # Use LLM router suggestions
        logger.debug(f"[FAST/UNDERSTAND] Using LLM router suggestions: {suggested_tools}")

        for priority, tool_name in enumerate(suggested_tools):
            # Skip conversation tool in queue (it's always called in respond_node)
            if tool_name == "conversation":
                continue

            # Only process fast brain tools
            if tool_name not in {"tavily_search", "timestamp_noter"}:
                continue

            params = suggested_params.get(tool_name, {})
            tool_queue.append(
                ToolCall(
                    tool_name=tool_name,
                    tool_type="fast",
                    params=params,
                    priority=priority + 1,
                )
            )
    else:
        # Fall back to regex-based tool decider
        tool_decision = tool_decider(current_input, state)

        if tool_decision.selected_tool != "none":
            tool_queue.append(
                ToolCall(
                    tool_name=tool_decision.selected_tool,
                    tool_type="fast",
                    params=tool_decision.params,
                    priority=tool_decision.priority,
                )
            )

    # Increment turn count
    turn_count = state.get("turn_count", 0) + 1

    # Add a starting note on first turn for timeline visibility
    timestamp_notes = list(state.get("timestamp_notes", []))
    if turn_count == 1:
        timestamp = datetime.now(timezone.utc).isoformat()
        video_seconds = _calculate_video_seconds(state, timestamp)
        timestamp_notes.append(
            TimestampNote(
                timestamp=timestamp,
                tag="topic_change",
                content="Interview started",
                turn_number=1,
                video_seconds=video_seconds,
            )
        )
        logger.info("[FAST/UNDERSTAND] Added interview start note to timeline")

    # Update DFA state
    dfa = state.get("dfa", {})
    if dfa:
        dfa = dict(dfa)
        dfa["current_state"] = "fast_processing"
        existing_transitions = list(dfa.get("transitions", []))
        dfa["transitions"] = existing_transitions + ["understand->fast_processing"]

    return {
        "turn_count": turn_count,
        "tool_queue": tool_queue,
        "timestamp_notes": timestamp_notes,
        "dfa": dfa,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


async def execute_tools_node(state: InterviewState) -> dict[str, Any]:
    """Execute any queued fast brain tools.

    Processes the tool queue in priority order.
    Tools are executed deterministically based on the queue.
    """
    tool_queue = state.get("tool_queue", [])
    tool_results = list(state.get("tool_results", []))
    tool_results_cache = dict(state.get("tool_results_cache", {}))

    session_id = state.get("session_id", "unknown")

    if not tool_queue:
        logger.debug(f"[FAST/TOOLS] Session {session_id}: No tools in queue")
        return {}

    # Sort by priority
    sorted_queue = sorted(tool_queue, key=lambda x: x.get("priority", 10))

    for tool_call in sorted_queue:
        tool_name = tool_call.get("tool_name", "")
        params = tool_call.get("params", {})

        logger.info(f"[FAST/TOOLS] Session {session_id}: Executing {tool_name}")

        try:
            result = None

            if tool_name == "tavily_search":
                query = params.get("query", state.get("current_input", "")[:100])
                result = await tavily_search_tool(query)

            elif tool_name == "timestamp_noter":
                result = await timestamp_noter_tool(
                    tag=params.get("tag", "key_insight"),
                    content=params.get("content", state.get("current_input", "")[:200]),
                    turn_number=state.get("turn_count", 0),
                    state=state,
                )

            if result:
                tool_result = ToolResult(
                    tool_name=tool_name,
                    input=str(params),
                    output=result.data if result.success else result.error,
                    success=result.success,
                    confidence=result.confidence,
                    source=result.source,
                    timestamp=result.timestamp,
                )
                tool_results.append(tool_result)

                # Cache result
                cache_key = f"{tool_name}:{hash(str(params))}"
                tool_results_cache[cache_key] = result.data

        except Exception as e:
            logger.error(f"[FAST/TOOLS] Tool {tool_name} failed: {e}")
            tool_results.append(
                ToolResult(
                    tool_name=tool_name,
                    input=str(params),
                    output=str(e),
                    success=False,
                    confidence=0.0,
                    source="error",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
            )

    # Update DFA state
    dfa = state.get("dfa", {})
    if dfa:
        dfa = dict(dfa)
        dfa["current_state"] = "tool_executing"

    return {
        "tool_queue": [],  # Clear the queue
        "tool_results": tool_results,
        "tool_results_cache": tool_results_cache,
        "dfa": dfa,
    }


async def respond_node(state: InterviewState) -> dict[str, Any]:
    """Generate the interviewer's response using conversation tool.

    Uses Gemini Flash for low-latency response generation.
    Also scores the candidate's response in real-time.

    DSA mode: When interview_mode == 'round2_dsa', dispatches to the
    DSA conversation tool instead of the general conversation tool.
    The DSA tool uses deterministic action selection + constrained LLM phrasing.
    """
    session_id = state.get("session_id", "unknown")
    current_input = state.get("current_input", "")
    interview_mode = state.get("interview_mode", "round1")

    logger.info(f"[FAST/RESPOND] Session {session_id}: Generating response (mode={interview_mode})")

    # -------------------------------------------------------------------------
    # DSA Round 2 — delegate to DSA conversation tool
    # -------------------------------------------------------------------------
    if interview_mode == "round2_dsa":
        try:
            from brain.tools.fast.dsa_conversation import dsa_conversation_tool
            dsa_result = await dsa_conversation_tool(state)
            response = dsa_result.get("response", "Let's continue — can you walk me through your approach?")
            dsa_state_update = dsa_result.get("dsa_state", state.get("dsa_state"))

            # Speak now; the evaluation below (up to 8s) only updates scoring state
            await publish_reply_early(response)

            # Add to message history
            messages = list(state.get("messages", []))
            timestamp = datetime.now(timezone.utc).isoformat()
            messages.append(Message(role="user", content=current_input, timestamp=timestamp))
            messages.append(Message(role="assistant", content=response, timestamp=timestamp))

            # Extract evidence inline (not via the slow-task queue: pending slow
            # tasks hijack the next turn's routing into the slow brain).
            # System inputs ([CODE EXECUTION], [NO ANSWER], ...) are not answers
            if current_input and not current_input.startswith("["):
                try:
                    import asyncio

                    from dsa.tools.slow.dsa_evaluator import evaluate_dsa_turn

                    eval_state = dict(state)
                    eval_state["messages"] = messages
                    eval_state["dsa_state"] = dsa_state_update
                    eval_result = await asyncio.wait_for(
                        evaluate_dsa_turn(state=eval_state, params={}), timeout=8
                    )
                    if eval_result and eval_result.get("dsa_state"):
                        dsa_state_update = eval_result["dsa_state"]
                except Exception as e:
                    logger.warning(f"[FAST/RESPOND/DSA] inline evaluation skipped: {e}")

            logger.info(
                f"[FAST/RESPOND/DSA] Session {session_id}: "
                f"action={( dsa_state_update or {}).get('last_action')}, "
                f"turn={( dsa_state_update or {}).get('dsa_turn_count')}"
            )

            return {
                "response": response,
                "messages": messages,
                "dsa_state": dsa_state_update,
                "last_updated": timestamp,
            }

        except Exception as e:
            logger.error(f"[FAST/RESPOND/DSA] DSA conversation tool failed: {e}, falling back to generic", exc_info=True)
            # Fallthrough to Round 1 path on error

    # -------------------------------------------------------------------------
    # Round 1 — original conversation tool (unchanged)
    # -------------------------------------------------------------------------

    # Call conversation tool
    result = await conversation_tool(state)

    if not result.success:
        logger.error(f"[FAST/RESPOND] Conversation tool failed: {result.error}")
        response = "That's interesting — could you tell me a bit more about that?"
        claims_detected: list[str] = []
        topics_touched: list[str] = []
    else:
        data = result.data
        response = data.get("response_text", "Could you tell me more about that?")
        claims_detected = data.get("claims_detected", [])
        topics_touched = data.get("topics_touched", [])

    # Speak now; response scoring and skill-tree scoring run after this
    await publish_reply_early(response)

    # Update message history
    messages = list(state.get("messages", []))
    timestamp = datetime.now(timezone.utc).isoformat()

    # Get the last assistant message as context for scoring
    interviewer_context = ""
    if messages:
        for msg in reversed(messages):
            if msg.get("role") == "assistant":
                interviewer_context = msg.get("content", "")
                break

    # Add user message
    messages.append(
        Message(
            role="user",
            content=current_input,
            timestamp=timestamp,
        )
    )

    # Add assistant response
    messages.append(
        Message(
            role="assistant",
            content=response,
            timestamp=timestamp,
        )
    )

    # Update topics covered
    topics_covered = list(state.get("topics_covered", []))
    for topic in topics_touched:
        if topic not in topics_covered:
            topics_covered.append(topic)

    # Queue claims for verification (will be handled by slow brain)
    pending_claims = list(state.get("pending_claims", []))
    for claim_text in claims_detected:
        pending_claims.append(
            Claim(
                id=str(uuid.uuid4()),
                claim_type="technology",  # Default type, can be refined later
                content=claim_text,
                source_text=current_input[:200],
                timestamp=timestamp,
            )
        )

    # Score the candidate's response in real-time
    running_scores = dict(state.get("running_scores", {}))
    timestamp_notes = list(state.get("timestamp_notes", []))

    try:
        score_result = await score_response(
            state=state,
            candidate_response=current_input,
            interviewer_context=interviewer_context,
        )

        if score_result.get("running_scores"):
            running_scores = score_result["running_scores"]
            logger.debug(f"[FAST/RESPOND] Updated running_scores: {running_scores}")

        # Add timestamp note if scorer detected notable response
        if score_result.get("add_timestamp_note"):
            note_data = score_result["add_timestamp_note"]
            video_secs = _calculate_video_seconds(state, note_data["timestamp"])
            timestamp_notes.append(
                TimestampNote(
                    timestamp=note_data["timestamp"],
                    tag=note_data["tag"],
                    content=note_data["content"],
                    turn_number=note_data["turn_number"],
                    video_seconds=video_secs,
                )
            )
            logger.info(
                f"[FAST/RESPOND] Added timestamp note: {note_data['tag']} at turn "
                f"{note_data['turn_number']}"
            )

    except Exception as e:
        logger.error(f"[FAST/RESPOND] Scoring failed (non-fatal): {e}")
        # Continue without scoring - don't break the interview

    # Add periodic topic notes to ensure timeline has content
    turn_count = state.get("turn_count", 0)
    if turn_count > 0 and turn_count % 3 == 0 and topics_touched:
        # Every 3 turns, add a topic progress note
        video_secs = _calculate_video_seconds(state, timestamp)
        timestamp_notes.append(
            TimestampNote(
                timestamp=timestamp,
                tag="topic_change",
                content=f"Topics covered: {', '.join(topics_touched[:3])}",
                turn_number=turn_count,
                video_seconds=video_secs,
            )
        )
        logger.debug(f"[FAST/RESPOND] Added periodic topic note at turn {turn_count}")

    # Trigger background claim verification (runs async, doesn't block response)
    # This replaces the previous slow task queueing approach for more reliable verification
    from brain.services.background_verifier import trigger_background_verification

    new_claims_count = len(pending_claims) - len(state.get("pending_claims", []))

    # Verify if: 3+ pending claims AND (new claims detected OR every 5th turn)
    should_verify = len(pending_claims) >= 3 and (new_claims_count > 0 or turn_count % 5 == 0)

    if should_verify:
        # Get claims that haven't been verified yet
        already_verified_ids = {
            v.get("claim", {}).get("id") for v in state.get("verified_claims", [])
        }
        unverified_claims = [c for c in pending_claims if c.get("id") not in already_verified_ids]

        if unverified_claims:
            trigger_background_verification(
                session_id=session_id,
                claims=unverified_claims,
                # Gathered background plus the resume as written
                candidate_profile=profile_for_checks(state),
            )
            logger.info(
                f"[FAST/RESPOND] Triggered background verification for "
                f"{len(unverified_claims)} claims"
            )

    # Update DFA state
    dfa = state.get("dfa", {})
    if dfa:
        dfa = dict(dfa)
        dfa["current_state"] = "responding"

    return {
        "messages": messages,
        "response": response,
        "topics_covered": topics_covered,
        "pending_claims": pending_claims,
        "running_scores": running_scores,
        "timestamp_notes": timestamp_notes,
        "dfa": dfa,
        "last_updated": timestamp,
    }


# =============================================================================
# Routing Functions
# =============================================================================


def should_execute_tools(state: InterviewState) -> str:
    """Determine if tools need to be executed."""
    tool_queue = state.get("tool_queue", [])
    if tool_queue:
        return "execute_tools"
    return "respond"


# =============================================================================
# Fast Brain Subgraph
# =============================================================================


def create_fast_brain_subgraph() -> StateGraph:
    """Create the fast brain subgraph for conversation handling.

    Flow:
        understand -> [tools?] -> execute_tools -> respond
                   -> [no tools] -> respond
    """
    graph = StateGraph(InterviewState)

    # Add nodes
    graph.add_node("understand", understand_node)
    graph.add_node("execute_tools", execute_tools_node)
    graph.add_node("respond", respond_node)

    # Add edges
    graph.set_entry_point("understand")

    # Conditional: check if tools need execution
    graph.add_conditional_edges(
        "understand",
        should_execute_tools,
        {
            "execute_tools": "execute_tools",
            "respond": "respond",
        },
    )

    graph.add_edge("execute_tools", "respond")
    graph.add_edge("respond", END)

    return graph


async def fast_brain_node(state: InterviewState) -> dict[str, Any]:
    """Single node wrapper for fast brain processing.

    This executes the fast brain subgraph as a single node
    for use in the main dual-brain graph.

    Now supports hybrid routing - uses tool suggestions from LLM router
    when available.
    """
    session_id = state.get("session_id", "unknown")
    routing_method = state.get("routing_method", "prefilter")
    suggested_tools = state.get("suggested_tools", [])

    logger.info(
        f"[FAST_BRAIN] Processing session {session_id} "
        f"(routing: {routing_method}, suggested_tools: {suggested_tools})"
    )

    try:
        # Execute understand phase
        understand_result = await understand_node(state)

        # Create merged state for subsequent nodes
        # Use InterviewState type hint to help with type checking
        merged_state: InterviewState = {**state, **understand_result}  # type: ignore

        # Execute tools if needed
        if merged_state.get("tool_queue"):
            tools_result = await execute_tools_node(merged_state)
            merged_state = {**merged_state, **tools_result}  # type: ignore

        # Generate response
        respond_result = await respond_node(merged_state)

        # Merge all results
        final_result = {
            **understand_result,
            **respond_result,
        }

        # Add tool results if they exist
        if "tool_results" in merged_state:
            final_result["tool_results"] = merged_state["tool_results"]
        if "tool_results_cache" in merged_state:
            final_result["tool_results_cache"] = merged_state["tool_results_cache"]

        logger.info(f"[FAST_BRAIN] Completed session {session_id}")
        return final_result

    except Exception as e:
        logger.error(f"[FAST_BRAIN] Error in session {session_id}: {e}")
        return {
            "response": "Could you elaborate a bit more on that?",
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
