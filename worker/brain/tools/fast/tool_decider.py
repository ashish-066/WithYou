"""Tool decider for fast brain.

Hybrid tool selection that combines:
1. LLM router suggestions (when available)
2. Regex-based fallback for when router suggestions are empty
"""

import logging
import re
from datetime import datetime, timezone
from typing import Any

from brain.models.schemas import FilteredToolOutput, ToolDecision
from brain.state import InterviewState

logger = logging.getLogger(__name__)


# =============================================================================
# Tool Selection Rules (Fallback Patterns)
# =============================================================================

# Patterns for tool selection when LLM suggestions are not available
SEARCH_PATTERNS = [
    r"\b(search|look\s*up|find|google)\b",
    r"\b(what\s+is|who\s+is|how\s+does)\b.{10,}",  # Informational questions
    r"\b(latest|recent|current)\b.*\b(news|updates|version)\b",
    r"\bhttps?://\S+\b",  # URLs mentioned
]

TIMESTAMP_PATTERNS = {
    "key_insight": [
        r"\b(key|important|critical|main)\s+(point|insight|takeaway)\b",
        r"\b(this\s+is\s+important)\b",
        r"\b(the\s+reason|because|since|therefore)\b.{20,}",  # Explanatory responses
        r"\b(in\s+my\s+experience|what\s+I've\s+learned)\b",
    ],
    "concern": [
        r"\b(concern|worried|issue|problem|red\s*flag)\b",
        r"\b(doesn't\s+match|inconsistent|discrepancy)\b",
        r"\b(never|haven't|don't\s+know|not\s+sure)\b.*\b(experience|worked|used)\b",
        r"\b(I\s+don't|I\s+haven't|I\s+can't)\b.{10,}",  # Admitting limitations
    ],
    "strong_answer": [
        r"\b(excellent|great|impressive|strong)\s+(answer|response|point)\b",
        r"\b(well\s+explained|clear\s+understanding)\b",
        r"\b(specifically|for\s+example|one\s+time)\b.{30,}",  # Specific examples
        r"\b(I\s+led|I\s+built|I\s+designed|I\s+architected)\b.{20,}",
        r"\b(resulted\s+in|achieved|improved\s+by|reduced\s+by)\b.{10,}\d+",  # Quantified
    ],
    "weak_answer": [
        r"\b(weak|vague|unclear|confusing)\s+(answer|response)\b",
        r"\b(didn't\s+answer|avoided)\b",
        r"^(yes|no|maybe|i\s+think\s+so)[.!?]?\s*$",  # Very short answers
        r"\b(um|uh|like|you\s+know)\b.*\b(um|uh|like|you\s+know)\b",  # Filler words
    ],
    "claim_made": [
        r"\b(I\s+(led|built|created|developed|managed|owned|architected|founded))\b",
        r"\b(at\s+\w+\s+(company|corp|inc|labs|technologies))\b",
        r"\b(\d+\s*(years?|months?)\s+(of\s+)?experience)\b",
        r"\b(I\s+worked\s+(at|for|with))\b.*\b(google|amazon|meta|microsoft|apple)\b",
        r"\b(grew|scaled|increased|reduced)\s+(by|to|from)\s*\d+",  # Metrics claims
    ],
    "topic_change": [
        r"\b(let's\s+(talk|discuss|move))\b",
        r"\b(changing\s+topic|next\s+question)\b",
        r"\b(speaking\s+of|that\s+reminds\s+me|also)\b",
    ],
}


# =============================================================================
# Tool Decider Implementation
# =============================================================================


def tool_decider(
    user_input: str,
    state: InterviewState | None = None,
    context: dict[str, Any] | None = None,
) -> ToolDecision:
    """Determine which tools should be used.

    This function now supports hybrid operation:
    1. First checks for LLM router suggestions in state
    2. Falls back to regex-based selection if no suggestions

    Args:
        user_input: The user's input text
        state: Optional interview state (contains LLM router suggestions)
        context: Optional additional context

    Returns:
        ToolDecision with selected tool and parameters
    """
    # Check for LLM router suggestions first
    if state is not None:
        suggested_tools = state.get("suggested_tools", [])
        suggested_params = state.get("suggested_tool_params", {})

        if suggested_tools:
            # Use LLM-suggested tools (filter to fast brain tools only)
            fast_brain_tools = {"conversation", "tavily_search", "timestamp_noter"}
            valid_tools = [t for t in suggested_tools if t in fast_brain_tools]

            if valid_tools:
                # Pick the first non-conversation tool if available
                # (conversation is always called anyway)
                selected = None
                for tool in valid_tools:
                    if tool != "conversation":
                        selected = tool
                        break

                if selected:
                    params = suggested_params.get(selected, {})
                    logger.debug(f"Tool decider: using LLM suggestion '{selected}'")

                    return ToolDecision(
                        selected_tool=selected,  # type: ignore
                        reason=f"LLM router suggested {selected}",
                        priority=1,
                        params=params,
                    )

    # Fall back to regex-based selection
    return _regex_tool_selection(user_input, state)


def _regex_tool_selection(
    user_input: str,
    state: InterviewState | None = None,
) -> ToolDecision:
    """Regex-based tool selection fallback.

    Used when LLM router suggestions are not available.
    """
    user_input_lower = user_input.lower()

    # Check for search patterns
    for pattern in SEARCH_PATTERNS:
        if re.search(pattern, user_input_lower):
            search_query = _extract_search_query(user_input)
            logger.debug(f"Tool decider: selected 'tavily_search' for query: {search_query}")

            return ToolDecision(
                selected_tool="tavily_search",
                reason=f"Search pattern detected: {pattern[:30]}",
                priority=1,
                params={"query": search_query},
            )

    # Check for timestamp patterns
    for tag, patterns in TIMESTAMP_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, user_input_lower):
                content = _extract_note_content(user_input, tag)
                turn_count = state.get("turn_count", 0) if state else 0

                logger.debug(f"Tool decider: selected 'timestamp_noter' with tag: {tag}")

                return ToolDecision(
                    selected_tool="timestamp_noter",
                    reason=f"Notable moment detected: {tag}",
                    priority=2,
                    params={
                        "tag": tag,
                        "content": content,
                        "turn_number": turn_count,
                    },
                )

    # Default: no additional tool needed (conversation will handle it)
    logger.debug("Tool decider: no additional tool needed")
    return ToolDecision(
        selected_tool="none",
        reason="Standard conversation, no additional tools required",
        priority=10,
        params={},
    )


async def tool_decider_async(
    state: InterviewState,
) -> FilteredToolOutput:
    """Async wrapper for tool_decider for use in LangGraph nodes.

    Args:
        state: Current interview state

    Returns:
        FilteredToolOutput containing ToolDecision
    """
    try:
        user_input = state.get("current_input", "")
        decision = tool_decider(user_input, state)

        return FilteredToolOutput(
            success=True,
            data=decision.model_dump(),
            confidence=1.0 if state.get("suggested_tools") else 0.8,
            source="tool_decider_hybrid" if state.get("suggested_tools") else "tool_decider_regex",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    except Exception as e:
        logger.error(f"Tool decider error: {e}")
        return FilteredToolOutput(
            success=False,
            data=ToolDecision(
                selected_tool="none",
                reason=f"Error in tool decision: {e}",
                priority=10,
                params={},
            ).model_dump(),
            confidence=0.0,
            source="tool_decider",
            error=str(e),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )


def get_tools_from_router_suggestions(state: InterviewState) -> list[ToolDecision]:
    """Get all tool decisions from LLM router suggestions.

    Returns a list of ToolDecisions for all suggested tools,
    useful when multiple tools should be executed.

    Args:
        state: Current interview state with router suggestions

    Returns:
        List of ToolDecision objects
    """
    suggested_tools = state.get("suggested_tools", [])
    suggested_params = state.get("suggested_tool_params", {})

    if not suggested_tools:
        return []

    fast_brain_tools = {"conversation", "tavily_search", "timestamp_noter"}
    decisions = []

    for priority, tool in enumerate(suggested_tools):
        if tool not in fast_brain_tools:
            continue

        params = suggested_params.get(tool, {})
        decisions.append(
            ToolDecision(
                selected_tool=tool,  # type: ignore
                reason=f"LLM router suggestion (priority {priority + 1})",
                priority=priority + 1,
                params=params,
            )
        )

    return decisions


# =============================================================================
# Helper Functions
# =============================================================================


def _extract_search_query(text: str) -> str:
    """Extract a search query from the input text."""
    query = text.lower()

    prefixes_to_remove = [
        r"^(can\s+you\s+)?(please\s+)?",
        r"^(search|look\s*up|find|google)\s+(for\s+)?",
        r"^(what\s+is|who\s+is|how\s+does)\s+",
    ]

    for prefix in prefixes_to_remove:
        query = re.sub(prefix, "", query, flags=re.IGNORECASE)

    return query.strip()[:100]


def _extract_note_content(text: str, tag: str) -> str:
    """Extract relevant content for a timestamp note."""
    # For claims, try to extract the specific claim
    if tag == "claim_made":
        match = re.search(
            r"I\s+(led|built|created|developed|managed|owned).{0,100}", text, re.IGNORECASE
        )
        if match:
            return match.group(0)[:200]

    # Default: use first 200 chars
    return text[:200]
