"""Citation tools for tracking interview evidence.

This module provides tools for marking and managing citations that link
interview moments to claims and verification results.
"""

import json
import logging
from datetime import datetime, timezone
from uuid import uuid4

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def mark_citation(
    claim_id: str, transcript_excerpt: str, timestamp_seconds: float, verdict: str
) -> str:
    """
    Mark a citation linking a claim to a specific moment in the interview.

    Args:
        claim_id: Unique ID of the claim.
        transcript_excerpt: The relevant transcript text.
        timestamp_seconds: Time in seconds into the interview.
        verdict: Verification verdict (verified, unverified, contradiction).

    Returns:
        JSON string with the citation record.
    """
    try:
        valid_verdicts = ["verified", "unverified", "contradiction"]

        if verdict.lower() not in valid_verdicts:
            return json.dumps(
                {
                    "error": f"Invalid verdict. Must be one of: {valid_verdicts}",
                }
            )

        citation = {
            "citation_id": str(uuid4()),
            "claim_id": claim_id,
            "transcript_excerpt": transcript_excerpt[:500],  # Limit excerpt length
            "timestamp_seconds": timestamp_seconds,
            "timestamp_formatted": format_timestamp(timestamp_seconds),
            "verdict": verdict.lower(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        return json.dumps(citation, indent=2)

    except Exception as e:
        logger.exception(f"Error marking citation: {e}")
        return json.dumps({"error": f"Failed to mark citation: {str(e)}"})


@tool
def get_all_citations(citations_json_array: str) -> str:
    """
    Format all citations for the final report.

    Args:
        citations_json_array: JSON array of citation records.

    Returns:
        Markdown formatted citations list.
    """
    try:
        citations = json.loads(citations_json_array)

        if not citations or not isinstance(citations, list):
            return "No citations recorded."

        # Sort by timestamp
        citations_sorted = sorted(citations, key=lambda x: x.get("timestamp_seconds", 0))

        # Build markdown
        markdown_lines = ["## Interview Citations", ""]

        for i, citation in enumerate(citations_sorted, 1):
            verdict = citation.get("verdict", "unknown")
            verdict_emoji = get_verdict_emoji(verdict)
            timestamp = citation.get("timestamp_formatted", "N/A")
            excerpt = citation.get("transcript_excerpt", "")

            markdown_lines.append(f"### Citation {i} {verdict_emoji}")
            markdown_lines.append(f"**Time:** {timestamp}")
            markdown_lines.append(f"**Verdict:** {verdict.replace('_', ' ').title()}")
            markdown_lines.append(f"**Claim ID:** `{citation.get('claim_id', 'N/A')}`")
            markdown_lines.append("")
            markdown_lines.append(f"> {excerpt}")
            markdown_lines.append("")

        return "\n".join(markdown_lines)

    except json.JSONDecodeError:
        return "Error: Invalid JSON provided for citations."
    except Exception as e:
        logger.exception(f"Error formatting citations: {e}")
        return f"Error formatting citations: {str(e)}"


@tool
def aggregate_citation_stats(citations_json_array: str) -> str:
    """
    Aggregate statistics from all citations.

    Args:
        citations_json_array: JSON array of citation records.

    Returns:
        JSON string with aggregated statistics.
    """
    try:
        citations = json.loads(citations_json_array)

        if not citations or not isinstance(citations, list):
            return json.dumps({"error": "No citations to aggregate."})

        verdict_counts = {
            "verified": 0,
            "unverified": 0,
            "contradiction": 0,
        }

        for citation in citations:
            verdict = citation.get("verdict", "").lower()
            if verdict in verdict_counts:
                verdict_counts[verdict] += 1

        total = len(citations)

        # Calculate trust score - only penalize contradictions
        # Trust starts at 1.0 and drops 15% per contradiction
        if total > 0:
            contradiction_count = verdict_counts["contradiction"]
            trust_score = max(0.0, 1.0 - (contradiction_count * 0.15))
        else:
            trust_score = 1.0

        result = {
            "total_citations": total,
            "verdict_breakdown": verdict_counts,
            "trust_score": round(trust_score, 3),
            "flags": [],
        }

        # Add flags for concerning patterns
        if verdict_counts["contradiction"] > 0:
            result["flags"].append(
                f"{verdict_counts['contradiction']} contradictions detected - review required"
            )
        if verdict_counts["unverified"] > total * 0.5:
            result["flags"].append("More than 50% of claims unverified")

        return json.dumps(result, indent=2)

    except json.JSONDecodeError:
        return json.dumps({"error": "Invalid JSON provided for citations."})
    except Exception as e:
        logger.exception(f"Error aggregating citations: {e}")
        return json.dumps({"error": f"Failed to aggregate citations: {str(e)}"})


def format_timestamp(seconds: float) -> str:
    """Format seconds into MM:SS format."""
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes:02d}:{secs:02d}"


def get_verdict_emoji(verdict: str) -> str:
    """Get emoji for verdict display."""
    emoji_map = {
        "verified": "✓",
        "unverified": "?",
        "contradiction": "✗",
    }
    return emoji_map.get(verdict.lower(), "?")
