"""Slow Brain subgraph: work that may take a while and never blocks a reply.

- Report generation (descriptive and analytics) when a session ends
- Deep analysis tasks
"""

import logging
from datetime import datetime, timezone
from typing import Any

from langgraph.graph import END, StateGraph

from brain.state import InterviewState, SlowTask, ToolResult
from brain.tools.slow.report_generator import generate_analytics_report, generate_descriptive_report

logger = logging.getLogger(__name__)


# =============================================================================
# Slow Brain Nodes
# =============================================================================


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def analyze_task_node(state: InterviewState) -> dict[str, Any]:
    """Queue the work to do: pending tasks, or the reports once the session ended."""
    session_id = state.get("session_id", "unknown")
    pending_tasks = state.get("pending_slow_tasks", [])

    logger.info(f"[SLOW/ANALYZE] Session {session_id}: {len(pending_tasks)} pending tasks")

    if not pending_tasks and (
        state.get("interview_ended") or state.get("input_classification") == "report_request"
    ):
        pending_tasks = [
            SlowTask(task_id="report_descriptive", task_type="report_descriptive",
                     params={}, priority=1, created_at=_now()),
            SlowTask(task_id="report_data", task_type="report_data",
                     params={}, priority=2, created_at=_now()),
        ]

    pending_tasks = sorted(pending_tasks, key=lambda x: x.get("priority", 10))

    dfa = state.get("dfa", {})
    if dfa:
        dfa = dict(dfa)
        dfa["current_state"] = "slow_processing"

    return {"pending_slow_tasks": pending_tasks, "dfa": dfa, "last_updated": _now()}


async def execute_slow_tasks_node(state: InterviewState) -> dict[str, Any]:
    """Run the queued tasks (reports, deep analysis)."""
    session_id = state.get("session_id", "unknown")
    pending_tasks = state.get("pending_slow_tasks", [])
    completed_tasks = state.get("completed_slow_tasks", []).copy()
    tool_results = state.get("tool_results", []).copy()
    updates: dict[str, Any] = {}

    for task in pending_tasks:
        if isinstance(task, str):
            task_id = task_type = task
            params: dict[str, Any] = {}
        elif isinstance(task, dict):
            task_id = task.get("task_id", "unknown")
            task_type = task.get("task_type", "")
            params = task.get("params", {}) or {}
        else:
            continue

        logger.info(f"[SLOW/EXECUTE] Session {session_id}: Executing {task_type}")

        try:
            result = None
            if task_type == "report_descriptive":
                result = await generate_descriptive_report(state)
                if result.success:
                    updates["descriptive_report"] = result.data
                    updates["report_status"] = "in_progress"

            elif task_type == "report_data":
                result = await generate_analytics_report(state)
                if result.success:
                    updates["analytics_data"] = result.data
                    if updates.get("descriptive_report") or state.get("descriptive_report"):
                        updates["report_status"] = "completed"

            elif task_type == "deep_analysis":
                result = await _perform_deep_analysis(state, params)

            if result:
                tool_results.append(
                    ToolResult(
                        tool_name=task_type,
                        input=str(params),
                        output=result.data if result.success else result.error,
                        success=result.success,
                        confidence=result.confidence,
                        source=result.source,
                        timestamp=result.timestamp,
                    )
                )
            completed_tasks.append(task_id)

        except Exception as e:
            logger.error(f"[SLOW/EXECUTE] Task {task_type} failed: {e}")
            tool_results.append(
                ToolResult(
                    tool_name=task_type, input=str(params), output=str(e), success=False,
                    confidence=0.0, source="error", timestamp=_now(),
                )
            )

    updates["pending_slow_tasks"] = []
    updates["completed_slow_tasks"] = completed_tasks
    updates["tool_results"] = tool_results
    return updates


async def slow_respond_node(state: InterviewState) -> dict[str, Any]:
    """A short reply after slow processing (only for explicit report requests)."""
    input_classification = state.get("input_classification", "")
    if input_classification == "report_request":
        report_status = state.get("report_status", "pending")
        if report_status == "completed":
            response = "The session summary is ready."
        elif report_status == "in_progress":
            response = "I'm still writing the session summary."
        else:
            response = "I'll write the session summary now."
    else:
        response = "Done. Shall we carry on?"

    dfa = state.get("dfa", {})
    if dfa:
        dfa = dict(dfa)
        dfa["current_state"] = "responding"

    return {"response": response, "dfa": dfa, "last_updated": _now()}


# =============================================================================
# Helper Functions
# =============================================================================


async def _perform_deep_analysis(
    state: InterviewState,
    params: dict[str, Any],
) -> Any:
    """Perform deep analysis using slow brain LLM."""
    from brain.models.llm_pool import get_llm_pool
    from brain.models.schemas import FilteredToolOutput

    try:
        pool = await get_llm_pool()
        client = pool.get_slow_client()

        prompt = f"""Perform a deep analysis of the interview data.
Analysis focus: {params.get("focus", "overall assessment")}

Interview context:
- Turn count: {state.get("turn_count", 0)}
- Topics: {state.get("topics_covered", [])}
- Trust score: {state.get("trust_score", 1.0)}

Provide a structured analysis."""

        response = await client.generate(prompt, max_tokens=1024)

        return FilteredToolOutput(
            success=True,
            data={"analysis": response},
            confidence=0.8,
            source="gemini_pro",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    except Exception as e:
        from brain.models.schemas import FilteredToolOutput

        return FilteredToolOutput(
            success=False,
            data=None,
            confidence=0.0,
            source="gemini_pro",
            error=str(e),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )


# =============================================================================
# Slow Brain Subgraph
# =============================================================================


def create_slow_brain_subgraph() -> StateGraph:
    """Flow: analyze -> execute_tasks -> respond"""
    graph = StateGraph(InterviewState)
    graph.add_node("analyze", analyze_task_node)
    graph.add_node("execute_tasks", execute_slow_tasks_node)
    graph.add_node("respond", slow_respond_node)
    graph.set_entry_point("analyze")
    graph.add_edge("analyze", "execute_tasks")
    graph.add_edge("execute_tasks", "respond")
    graph.add_edge("respond", END)
    return graph


async def slow_brain_node(state: InterviewState) -> dict[str, Any]:
    """The slow brain subgraph run as a single node of the main graph."""
    session_id = state.get("session_id", "unknown")
    logger.info(f"[SLOW_BRAIN] Processing session {session_id}")

    try:
        analyze_result = await analyze_task_node(state)
        merged_state = {**state, **analyze_result}
        tasks_result = await execute_slow_tasks_node(merged_state)
        merged_state = {**merged_state, **tasks_result}
        respond_result = await slow_respond_node(merged_state)
        logger.info(f"[SLOW_BRAIN] Completed session {session_id}")
        return {**analyze_result, **tasks_result, **respond_result}

    except Exception as e:
        logger.error(f"[SLOW_BRAIN] Error in session {session_id}: {e}")
        return {
            "response": "Sorry, something went wrong on my side. Shall we carry on?",
            "last_updated": _now(),
        }
