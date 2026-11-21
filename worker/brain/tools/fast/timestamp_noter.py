"""Timestamp noter tool for fast brain.

Records important moments during the interview with tags.
"""

import logging
from datetime import datetime, timezone
from typing import Literal

from brain.models.schemas import FilteredToolOutput, TimestampNoteOutput
from brain.state import InterviewState, TimestampNote

logger = logging.getLogger(__name__)


# =============================================================================
# Tool Implementation
# =============================================================================


async def timestamp_noter_tool(
    tag: Literal[
        "key_insight",
        "concern",
        "strong_answer",
        "weak_answer",
        "claim_made",
        "topic_change",
    ],
    content: str,
    turn_number: int,
    state: InterviewState | None = None,
) -> FilteredToolOutput:
    """Record an important moment during the interview.

    This tool is designed for:
    - Quick note-taking during conversation
    - Tagging moments for later review
    - Building interview timeline

    Args:
        tag: Type of moment being noted
        content: Brief description (max 200 chars)
        turn_number: Current turn in the interview
        state: Optional interview state for context

    Returns:
        FilteredToolOutput containing TimestampNoteOutput
    """
    try:
        timestamp = datetime.now(timezone.utc).isoformat()

        # Truncate content if too long
        content = content[:200] if len(content) > 200 else content

        output = TimestampNoteOutput(
            timestamp=timestamp,
            tag=tag,
            content=content,
            turn_number=turn_number,
            created=True,
        )

        logger.debug(f"Timestamp note created: [{tag}] {content[:50]}...")

        return FilteredToolOutput(
            success=True,
            data=output.model_dump(),
            confidence=1.0,  # Deterministic operation
            source="timestamp_noter",
            timestamp=timestamp,
        )

    except Exception as e:
        logger.error(f"Timestamp noter error: {e}")
        return FilteredToolOutput(
            success=False,
            data=None,
            confidence=0.0,
            source="timestamp_noter",
            error=str(e),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )


def create_timestamp_note(
    tag: str,
    content: str,
    turn_number: int,
) -> TimestampNote:
    """Create a TimestampNote for state updates.

    This is a helper function for creating notes directly.
    """
    return TimestampNote(
        timestamp=datetime.now(timezone.utc).isoformat(),
        tag=tag,  # type: ignore
        content=content[:200],
        turn_number=turn_number,
    )
