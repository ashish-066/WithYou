"""Brain layer - Dual-Brain LangGraph Interview Agent.

This package implements the dual-brain architecture for scalable,
low-latency interview processing:

- Fast Brain: Gemini Flash for conversation (low latency)
- Slow Brain: Gemini Pro for analysis and reports (high quality)
- DFA Router: Deterministic routing for zero hallucination

Usage:
    from brain import create_interview_graph, InterviewState

    graph = create_interview_graph()
    result = await graph.ainvoke(state, config={"configurable": {"thread_id": session_id}})
"""

from brain.graph import (
    create_dual_brain_graph,
    create_interview_graph,
    get_graph_diagram,
    process_message,
)
from brain.state import (
    InterviewState,
    create_default_dfa_state,
    create_default_interview_state,
)

__all__ = [
    # Graph creation
    "create_interview_graph",
    "create_dual_brain_graph",
    "process_message",
    "get_graph_diagram",
    # State
    "InterviewState",
    "create_default_interview_state",
    "create_default_dfa_state",
]
