"""Real-time response scoring tool.

This module provides lightweight scoring of candidate responses during
the interview, updating running_scores after each turn.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from brain.models.llm_pool import get_llm_pool
from brain.state import InterviewState, RunningScores

logger = logging.getLogger(__name__)


def _calculate_video_seconds(started_at: str | None, timestamp: str) -> float | None:
    """Calculate elapsed seconds from interview start for video synchronization.

    Args:
        started_at: Interview start timestamp in ISO format
        timestamp: The current timestamp in ISO format

    Returns:
        Elapsed seconds from interview start, or None if calculation fails
    """
    try:
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


# Schema for structured output
SCORE_SCHEMA = {
    "type": "object",
    "properties": {
        "technical_depth": {
            "type": "number",
            "description": "Technical depth (0-5), null if not applicable",
        },
        "problem_solving": {
            "type": "number",
            "description": "Problem solving (0-5), null if not applicable",
        },
        "communication": {
            "type": "number",
            "description": "Communication clarity (0-5)",
        },
        "experience_fit": {
            "type": "number",
            "description": "Experience relevance (0-5), null if not applicable",
        },
        "cultural_alignment": {
            "type": "number",
            "description": "Cultural fit (0-5), null if not applicable",
        },
        "response_quality": {
            "type": "string",
            "enum": ["strong", "good", "neutral", "weak", "concerning"],
        },
    },
}


SCORING_PROMPT = """You are evaluating a candidate's interview response in real-time.

Current Interview Context:
- Turn: {turn_count}
- Current Topic: {current_topic}
- Topics Covered: {topics_covered}

Previous Running Scores (if any):
{previous_scores}

Candidate's Latest Response:
"{candidate_response}"

Interviewer's Question/Context:
"{interviewer_context}"

Rate this specific response on the following dimensions (0-5 scale, use decimals):
- technical_depth: Technical knowledge demonstrated (null if not technical)
- problem_solving: Problem-solving approach shown (null if not applicable)
- communication: Clarity and articulation (always rate this)
- experience_fit: Relevance of shared experience (null if no experience discussed)
- cultural_alignment: Team/culture fit signals (null if not applicable)

Also classify the overall response_quality as: strong, good, neutral, weak, or concerning.

Important:
- Only rate dimensions that are relevant to this specific response
- Use null for dimensions that can't be assessed from this response
- Communication should almost always be rated
- Be calibrated: 3.0 is average, 4.0 is good, 5.0 is exceptional
- Consider this is a running evaluation - scores will be averaged over time

Respond in JSON format:
{{
    "technical_depth": <number or null>,
    "problem_solving": <number or null>,
    "communication": <number>,
    "experience_fit": <number or null>,
    "cultural_alignment": <number or null>,
    "response_quality": "<strong|good|neutral|weak|concerning>"
}}"""


async def score_response(
    state: InterviewState,
    candidate_response: str,
    interviewer_context: str = "",
) -> dict[str, Any]:
    """Score a candidate's response and return updated running scores.

    Args:
        state: Current interview state
        candidate_response: The candidate's latest response
        interviewer_context: The question or context that prompted the response

    Returns:
        Dictionary with updated running_scores and any timestamp notes to add
    """
    session_id = state.get("session_id", "unknown")
    turn_count = state.get("turn_count", 0)

    logger.debug(f"[SCORER] Scoring response for session {session_id}, turn {turn_count}")

    try:
        # Get previous scores
        previous_scores = state.get("running_scores", {})
        previous_scores_str = (
            "\n".join(f"  {k}: {v}" for k, v in previous_scores.items())
            if previous_scores
            else "No previous scores yet"
        )

        # Build prompt
        prompt = SCORING_PROMPT.format(
            turn_count=turn_count,
            current_topic=state.get("current_topic", "general"),
            topics_covered=", ".join(state.get("topics_covered", [])) or "none yet",
            previous_scores=previous_scores_str,
            candidate_response=candidate_response[:1000],  # Limit length
            interviewer_context=(interviewer_context[:500] if interviewer_context else "N/A"),
        )

        # Use the LLM pool for fast scoring
        pool = await get_llm_pool()
        client = pool.get_client("fast")

        # Get structured output
        score_data = await client.generate_with_schema(
            prompt=prompt,
            response_schema=SCORE_SCHEMA,
        )

        # Extract response quality
        response_quality = score_data.get("response_quality", "neutral")

        # Merge with existing scores using exponential moving average
        updated_scores = _merge_scores(previous_scores, score_data, turn_count)

        logger.info(
            f"[SCORER] Session {session_id}: response_quality={response_quality}, "
            f"scores={updated_scores}"
        )

        result: dict[str, Any] = {
            "running_scores": updated_scores,
        }

        # Add timestamp note for notable responses (strong, good, weak, or concerning)
        # Expanded to capture more moments on timeline for video sync
        note_tag_map = {
            "strong": "strong_answer",
            "good": "key_insight",
            "weak": "weak_answer",
            "concerning": "concern",
        }

        if response_quality in note_tag_map:
            tag = note_tag_map[response_quality]
            timestamp = datetime.now(timezone.utc).isoformat()
            started_at = state.get("started_at")
            video_seconds = _calculate_video_seconds(started_at, timestamp)

            result["add_timestamp_note"] = {
                "timestamp": timestamp,
                "tag": tag,
                "content": candidate_response[:200],
                "turn_number": turn_count,
                "video_seconds": video_seconds,
            }
            logger.debug(
                f"[SCORER] Adding timestamp note: tag={tag}, "
                f"video_seconds={video_seconds}"
            )

        return result

    except json.JSONDecodeError as e:
        logger.error(f"[SCORER] JSON parse error for session {session_id}: {e}")
        return {}
    except Exception as e:
        logger.error(f"[SCORER] Error scoring response for session {session_id}: {e}")
        # Return empty update on error - don't break the interview flow
        return {}


def _merge_scores(
    previous: RunningScores,
    update: dict[str, Any],
    turn_count: int,
) -> RunningScores:
    """Merge new scores with previous using exponential moving average.

    Args:
        previous: Previous running scores
        update: New score update from LLM
        turn_count: Current turn number

    Returns:
        Updated running scores
    """
    # Weight for new observation - decreases as interview progresses
    # Early turns have more impact, later turns smooth out
    alpha = max(0.3, 1.0 / (turn_count + 1))

    merged: RunningScores = dict(previous)  # type: ignore

    dimensions = [
        "technical_depth",
        "problem_solving",
        "communication",
        "experience_fit",
        "cultural_alignment",
    ]

    for dim in dimensions:
        new_value = update.get(dim)
        if new_value is not None and isinstance(new_value, (int, float)):
            old_value = merged.get(dim)  # type: ignore
            if old_value is not None:
                # Exponential moving average
                merged[dim] = round(  # type: ignore
                    old_value * (1 - alpha) + new_value * alpha, 2
                )
            else:
                # First observation for this dimension
                merged[dim] = round(new_value, 2)  # type: ignore

    return merged
