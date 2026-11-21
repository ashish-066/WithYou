"""Brain tools: fast (conversation) and slow (reports)."""

from brain.tools.fast import conversation_tool, timestamp_noter_tool, tool_decider
from brain.tools.slow import generate_analytics_report, generate_descriptive_report

__all__ = [
    "conversation_tool",
    "timestamp_noter_tool",
    "tool_decider",
    "generate_descriptive_report",
    "generate_analytics_report",
]
