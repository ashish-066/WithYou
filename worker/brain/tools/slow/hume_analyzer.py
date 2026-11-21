"""Hume.AI Emotional Analysis Tool for Interview Recordings.

This tool processes interview videos through Hume.AI's voice prosody model
to extract emotional patterns and generate insights.
"""

import logging
from datetime import datetime, timezone
from typing import Any

import numpy as np

from brain.models.schemas import FilteredToolOutput
from brain.state import EmotionalInsights, EmotionalTimepoint, InterviewState
from core.hume_client import get_hume_client

logger = logging.getLogger(__name__)


# =============================================================================
# Emotion Mapping (Hume's 48 emotions -> 4 key metrics)
# =============================================================================

# Emotions that indicate confidence
CONFIDENCE_EMOTIONS = {
    "high": ["Determination", "Triumph", "Pride", "Satisfaction", "Realization"],
    "low": ["Anxiety", "Fear", "Doubt", "Awkwardness", "Confusion", "Embarrassment"],
}

# Emotions that indicate stress
STRESS_EMOTIONS = {
    "high": ["Anxiety", "Distress", "Fear", "Pain", "Tiredness", "Awkwardness"],
    "low": ["Calmness", "Relief", "Contentment", "Satisfaction", "Relaxation"],
}

# Emotions that indicate engagement
ENGAGEMENT_EMOTIONS = {
    "high": ["Interest", "Excitement", "Amusement", "Joy", "Surprise (positive)", "Concentration"],
    "low": ["Boredom", "Tiredness", "Contempt", "Disappointment"],
}

# Emotions that indicate energy
ENERGY_EMOTIONS = {
    "high": ["Excitement", "Joy", "Amusement", "Ecstasy", "Exhilaration"],
    "low": ["Sadness", "Tiredness", "Calmness", "Boredom"],
}


def _calculate_metric_score(
    emotions: dict[str, float], metric_emotions: dict[str, list[str]]
) -> float:
    """Calculate a 0-1 metric score from emotion scores.

    Args:
        emotions: Dict of emotion_name -> score (0-1)
        metric_emotions: Dict with "high" and "low" emotion lists

    Returns:
        Aggregated score 0-1 (higher = more of this metric)
    """
    high_scores = [emotions.get(em, 0.0) for em in metric_emotions["high"]]
    low_scores = [emotions.get(em, 0.0) for em in metric_emotions["low"]]

    avg_high = np.mean(high_scores) if high_scores else 0.0
    avg_low = np.mean(low_scores) if low_scores else 0.0

    # Normalize: high emotions increase score, low emotions decrease it
    # Map from [-1, 1] to [0, 1]
    score = (avg_high - avg_low + 1.0) / 2.0
    return float(np.clip(score, 0.0, 1.0))


def _parse_hume_results(raw_results: Any) -> EmotionalInsights:
    """Convert Hume API response to structured insights.

    Hume prosody returns 48 emotions per time window.
    We aggregate into 4 key metrics: confidence, stress, engagement, energy.

    Args:
        raw_results: Raw predictions from Hume API

    Returns:
        Structured EmotionalInsights
    """
    timeline: list[EmotionalTimepoint] = []

    # Parse Hume results structure
    try:
        # Hume returns list with one item per file
        if not raw_results or len(raw_results) == 0:
            raise ValueError("Empty results from Hume API")

        file_results = raw_results[0]

        # Navigate to prosody predictions
        predictions = file_results.get("results", {}).get("predictions", [])

        for prediction in predictions:
            prosody_results = prediction.get("models", {}).get("prosody", {})
            grouped_predictions = prosody_results.get("grouped_predictions", [])

            for segment in grouped_predictions:
                for frame in segment.get("predictions", []):
                    # Extract timestamp
                    time_info = frame.get("time", {})
                    timestamp = time_info.get("begin", 0.0)

                    # Extract emotion scores
                    emotions_list = frame.get("emotions", [])
                    emotions = {e["name"]: e["score"] for e in emotions_list}

                    # Calculate 4 key metrics
                    confidence = _calculate_metric_score(emotions, CONFIDENCE_EMOTIONS)
                    stress = _calculate_metric_score(emotions, STRESS_EMOTIONS)
                    engagement = _calculate_metric_score(emotions, ENGAGEMENT_EMOTIONS)
                    energy = _calculate_metric_score(emotions, ENERGY_EMOTIONS)

                    timeline.append(
                        EmotionalTimepoint(
                            timestamp=float(timestamp),
                            confidence=confidence,
                            stress=stress,
                            engagement=engagement,
                            energy=energy,
                        )
                    )

    except Exception as e:
        logger.error(f"Failed to parse Hume results: {e}")
        # Return empty timeline if parsing fails
        timeline = []

    # Calculate summary statistics
    if timeline:
        summary = {
            "avg_confidence": float(np.mean([t["confidence"] for t in timeline])),
            "avg_stress": float(np.mean([t["stress"] for t in timeline])),
            "avg_engagement": float(np.mean([t["engagement"] for t in timeline])),
            "avg_energy": float(np.mean([t["energy"] for t in timeline])),
        }
    else:
        summary = {
            "avg_confidence": 0.0,
            "avg_stress": 0.0,
            "avg_engagement": 0.0,
            "avg_energy": 0.0,
        }

    # Extract highlights (peaks and dips in emotions)
    highlights = _extract_highlights(timeline)

    # Determine overall emotional profile
    overall_profile = _determine_profile(summary)

    return EmotionalInsights(
        summary=summary,
        timeline=timeline,
        highlights=highlights,
        overall_profile=overall_profile,
    )


def _extract_highlights(timeline: list[EmotionalTimepoint]) -> list[str]:
    """Identify key emotional moments in the timeline.

    Args:
        timeline: List of emotional timepoints

    Returns:
        List of highlight descriptions
    """
    if not timeline or len(timeline) < 10:
        return []

    highlights = []

    # Find confidence spikes (top 10th percentile)
    confidence_scores = [t["confidence"] for t in timeline]
    confidence_threshold = np.percentile(confidence_scores, 90)

    for t in timeline:
        if t["confidence"] >= confidence_threshold:
            minutes = int(t["timestamp"] // 60)
            seconds = int(t["timestamp"] % 60)
            highlights.append(
                f"High confidence spike at {minutes}:{seconds:02d} (score: {t['confidence']:.2f})"
            )
            break  # Only report first major spike

    # Find stress peaks
    stress_scores = [t["stress"] for t in timeline]
    stress_threshold = np.percentile(stress_scores, 90)

    for t in timeline:
        if t["stress"] >= stress_threshold:
            minutes = int(t["timestamp"] // 60)
            seconds = int(t["timestamp"] % 60)
            highlights.append(
                f"Elevated stress at {minutes}:{seconds:02d} (score: {t['stress']:.2f})"
            )
            break

    # Check for consistent engagement
    avg_engagement = np.mean([t["engagement"] for t in timeline])
    if avg_engagement > 0.6:
        highlights.append(f"Consistent engagement throughout (avg: {avg_engagement:.2f})")

    return highlights[:5]  # Limit to 5 highlights


def _determine_profile(summary: dict[str, float]) -> str:
    """Determine overall emotional profile from summary stats.

    Args:
        summary: Summary statistics

    Returns:
        Profile label: confident, anxious, neutral, or variable
    """
    confidence = summary["avg_confidence"]
    stress = summary["avg_stress"]

    if confidence > 0.6 and stress < 0.4:
        return "confident"
    elif stress > 0.6 or confidence < 0.3:
        return "anxious"
    elif abs(confidence - 0.5) < 0.1 and abs(stress - 0.5) < 0.1:
        return "neutral"
    else:
        return "variable"


# =============================================================================
# Main Tool Function
# =============================================================================


async def hume_analyzer_tool(
    state: InterviewState,
    video_url: str | None = None,
    job_id: str | None = None,
) -> FilteredToolOutput:
    """Analyze interview video for emotional patterns using Hume.AI.

    This tool has 3 stages:
    1. Submit video to Hume API (returns job_id)
    2. Poll for completion (returns status)
    3. Parse results into timeline + summary

    Args:
        state: Current interview state
        video_url: URL of video to analyze (required for initial submission)
        job_id: Existing Hume job ID for status checking

    Returns:
        FilteredToolOutput with analysis results or status
    """
    try:
        session_id = state.get("session_id", "unknown")

        logger.info(
            f"[HUME_DEBUG] hume_analyzer_tool called: session={session_id}, "
            f"video_url={video_url}, job_id={job_id}"
        )

        hume = await get_hume_client()

        # Stage 1: Submit new job
        if not job_id:
            if not video_url:
                logger.error(f"[HUME_DEBUG] No video_url provided for session {session_id}")
                return FilteredToolOutput(
                    success=False,
                    data=None,
                    confidence=0.0,
                    source="hume_ai",
                    error="video_url required for initial submission",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )

            logger.info(
                f"[HUME_DEBUG] Submitting video for analysis: {session_id}, url={video_url}"
            )
            job_id = await hume.submit_video_for_analysis(
                video_url=video_url, session_id=session_id
            )

            logger.info(f"[HUME_DEBUG] Job submitted: session={session_id}, job_id={job_id}")
            return FilteredToolOutput(
                success=True,
                data={"job_id": job_id, "status": "QUEUED"},
                confidence=1.0,
                source="hume_ai",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        # Stage 2: Check status
        logger.info(f"[HUME_DEBUG] Checking status for job_id={job_id}")
        status = await hume.get_job_status(job_id)
        logger.info(f"[HUME_DEBUG] Job {job_id} status: {status}")

        if status in ["QUEUED", "IN_PROGRESS"]:
            return FilteredToolOutput(
                success=True,
                data={"job_id": job_id, "status": status},
                confidence=1.0,
                source="hume_ai",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        if status == "FAILED":
            logger.error(f"[HUME_DEBUG] Job {job_id} FAILED")
            return FilteredToolOutput(
                success=False,
                data={"job_id": job_id, "status": "FAILED"},
                confidence=0.0,
                source="hume_ai",
                error="Hume job failed",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        # Stage 3: Fetch and parse results
        logger.info(f"[HUME_DEBUG] Fetching results for job {job_id}")
        raw_results = await hume.get_results(job_id)

        logger.info(
            f"[HUME_DEBUG] Got raw results for job {job_id}: "
            f"{len(raw_results) if raw_results else 0} items"
        )

        # Parse into structured insights
        insights = _parse_hume_results(raw_results)

        logger.info(
            f"[HUME_DEBUG] Analysis complete for {session_id}: "
            f"profile={insights['overall_profile']}, "
            f"avg_confidence={insights['summary']['avg_confidence']:.2f}, "
            f"timeline_points={len(insights['timeline'])}"
        )

        return FilteredToolOutput(
            success=True,
            data=insights,
            confidence=1.0,
            source="hume_ai",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    except Exception as e:
        logger.error(f"[HUME_DEBUG] Error in emotional analysis: {e}", exc_info=True)
        return FilteredToolOutput(
            success=False,
            data=None,
            confidence=0.0,
            source="hume_ai",
            error=str(e),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
