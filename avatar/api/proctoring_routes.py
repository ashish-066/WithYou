"""Proctoring API routes for anti-cheating functionality.

Provides endpoints for:
- Submitting cheat flags from client-side detection
- Querying integrity status for a session
- Generating integrity reports
"""

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException

from api.proctoring_schemas import (
    BatchCheatFlagRequest,
    BatchCheatFlagResponse,
    CheatFlagRequest,
    CheatFlagResponse,
    IntegrityReportResponse,
    IntegrityStatusResponse,
)
from core.auth import (
    Candidate,
    User,
    ensure_session_access,
    ensure_session_user_access,
    optional_candidate,
    optional_user,
    require_signed_in,
    require_user,
)
from core.config import settings
from core.rate_limit import rate_limit
from core.redis import get_redis_client
from services.streams import AvatarStreamManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/proctoring", tags=["Proctoring"])

# Redis key patterns - use settings for consistency with other services
CONTEXT_KEY_PREFIX = settings.context_prefix

# Flag type to human-readable description mapping for timeline notes
FLAG_DESCRIPTIONS = {
    "multiple_faces": "Multiple faces detected",
    "no_face": "No face detected in frame",
    "phone_detected": "Phone detected in frame",
    "earphone_detected": "Earphone/earbud detected",
    "tab_switch": "Browser tab switched",
    "screen_share": "Screen sharing detected",
    "voice_change": "Voice change detected",
    "copy_paste": "Copy-paste detected",
    "ai_assistance": "AI assistance suspected",
    "suspicious_timing": "Suspicious response timing",
    "blocked_app": "Blocked app open",
    "second_screen": "Extra screen connected",
    "app_closed": "App closed before submitting",
    "exit_attempt": "Tried to close the app",
    "emergency_exit": "Emergency exit used",
    "lock_expired": "App lock reached its time limit",
    "browser_mode": "Taken without the locked app",
}


# =============================================================================
# Helper Functions
# =============================================================================


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


async def _get_session_state(redis, session_id: str) -> dict | None:
    """Get session state from Redis hash."""
    key = f"{CONTEXT_KEY_PREFIX}:{session_id}"
    data = await redis.hgetall(key)
    if not data:
        return None
    return data


def _timeline_note(flag: dict, started_at: str | None) -> dict:
    """Timeline note shown in the recruiter's session view for a flag."""
    flag_description = FLAG_DESCRIPTIONS.get(flag["flag_type"], flag["flag_type"])
    note_content = flag_description
    if flag.get("description"):
        note_content = f"{flag_description}: {flag['description']}"
    return {
        "timestamp": flag["timestamp"],
        "tag": "concern",
        "content": note_content,
        "turn_number": flag.get("turn_number", 0),
        "video_seconds": _calculate_video_seconds(started_at, flag["timestamp"]),
    }


async def _queue_flags(session_id: str, flags: list[dict], notes: list[dict]) -> None:
    """Hand flags to the brain worker, which applies them under the session lock.

    Writing the session state here directly raced with the worker, which saves
    its whole copy of the state at the end of each turn and would drop flags
    recorded in the meantime.
    """
    redis = get_redis_client()
    try:
        await AvatarStreamManager(redis).publish_transcription(
            session_id=session_id,
            content="",
            message_type="proctoring_flags",
            extra_fields={"flags": flags, "notes": notes},
        )
    finally:
        await redis.aclose()


def _calculate_integrity_score(flags: list[dict]) -> float:
    """Calculate integrity score based on accumulated flags.

    This mirrors the logic in worker/services/anti_cheat.py.
    """
    if not flags:
        return 1.0

    # Weight multipliers for each flag type
    flag_weights = {
        "multiple_faces": 0.15,
        "no_face": 0.05,
        "phone_detected": 0.12,
        "earphone_detected": 0.10,
        "tab_switch": 0.08,
        "screen_share": 0.15,
        "voice_change": 0.12,
        "copy_paste": 0.10,
        "ai_assistance": 0.15,
        "suspicious_timing": 0.05,
        "blocked_app": 0.12,
        "second_screen": 0.12,
        "app_closed": 0.12,
        "exit_attempt": 0.02,
        "emergency_exit": 0.08,
        "lock_expired": 0.01,
        "browser_mode": 0.05,
    }

    severity_multipliers = {
        "low": 0.5,
        "medium": 1.0,
        "high": 1.5,
        "critical": 2.0,
    }

    type_counts: dict[str, int] = {}
    total_penalty = 0.0

    for flag in flags:
        flag_type = flag.get("flag_type", "")
        severity = flag.get("severity", "medium")
        confidence = flag.get("confidence", 0.5)

        base_weight = flag_weights.get(flag_type, 0.05)
        severity_mult = severity_multipliers.get(severity, 1.0)
        confidence_mult = confidence

        type_counts[flag_type] = type_counts.get(flag_type, 0) + 1
        repetition_factor = 1.0 / (1.0 + 0.3 * (type_counts[flag_type] - 1))

        penalty = base_weight * severity_mult * confidence_mult * repetition_factor
        total_penalty += penalty

    return max(0.0, min(1.0, round(1.0 - total_penalty, 3)))


RecommendationType = Literal["proceed", "review", "flag", "reject"]


def _get_recommendation(
    integrity_score: float,
    flags_by_severity: dict[str, int],
) -> RecommendationType:
    """Determine integrity recommendation based on score and flags."""
    critical_count = flags_by_severity.get("critical", 0)
    high_count = flags_by_severity.get("high", 0)

    if critical_count >= 2:
        return "reject"
    if critical_count >= 1 and high_count >= 2:
        return "reject"

    if integrity_score >= 0.85:
        return "proceed"
    elif integrity_score >= 0.70:
        return "review"
    elif integrity_score >= 0.50:
        return "flag"
    else:
        return "reject"


# =============================================================================
# Endpoints
# =============================================================================


@router.post(
    "/flags",
    response_model=CheatFlagResponse,
    dependencies=[Depends(require_signed_in), Depends(rate_limit("proctoring_flags", 120, 60))],
)
async def report_cheat_flag(
    request: CheatFlagRequest,
    user: User | None = Depends(optional_user),
    candidate: Candidate | None = Depends(optional_candidate),
):
    """Report a single cheat flag detected during the interview.

    This endpoint is called by the client-side proctoring system
    when a potential cheating indicator is detected.
    """
    await ensure_session_access(request.session_id, user, candidate)
    redis = get_redis_client()

    try:
        # Verify session exists
        state = await _get_session_state(redis, request.session_id)
        if not state:
            raise HTTPException(status_code=404, detail="Session not found")

        # Get current turn count
        turn_count = int(state.get("turn_count", b"0"))

        # Get started_at for video timestamp calculation
        started_at = state.get("started_at")
        if isinstance(started_at, bytes):
            started_at = started_at.decode("utf-8")

        # Create flag record
        flag_id = str(uuid.uuid4())
        recorded_at = datetime.now(UTC).isoformat()

        new_flag = {
            "id": flag_id,
            "flag_type": request.flag_type,
            "severity": request.severity,
            "confidence": request.confidence,
            "description": request.description,
            "evidence": request.evidence,
            "timestamp": recorded_at,
            "turn_number": turn_count,
            "client_timestamp": request.client_timestamp,
        }

        # Get existing flags to calculate new score
        existing_flags_raw = await redis.hget(
            f"{CONTEXT_KEY_PREFIX}:{request.session_id}", "cheat_flags"
        )
        if existing_flags_raw:
            try:
                existing_flags = json.loads(existing_flags_raw)
            except json.JSONDecodeError:
                existing_flags = []
        else:
            existing_flags = []

        all_flags = existing_flags + [new_flag]
        integrity_score = _calculate_integrity_score(all_flags)

        # Recorded by the brain worker (in order, under the session lock)
        await _queue_flags(request.session_id, [new_flag], [_timeline_note(new_flag, started_at)])

        logger.info(
            f"Cheat flag recorded: session={request.session_id}, "
            f"type={request.flag_type}, severity={request.severity}, "
            f"integrity={integrity_score:.2f}"
        )

        return CheatFlagResponse(
            flag_id=flag_id,
            session_id=request.session_id,
            flag_type=request.flag_type,
            severity=request.severity,
            recorded_at=recorded_at,
            integrity_score=integrity_score,
        )

    finally:
        await redis.aclose()


@router.post(
    "/flags/batch",
    response_model=BatchCheatFlagResponse,
    dependencies=[Depends(require_signed_in), Depends(rate_limit("proctoring_flags", 120, 60))],
)
async def report_cheat_flags_batch(
    request: BatchCheatFlagRequest,
    user: User | None = Depends(optional_user),
    candidate: Candidate | None = Depends(optional_candidate),
):
    """Report multiple cheat flags in a single request.

    Useful for batching detections to reduce network overhead.
    """
    await ensure_session_access(request.session_id, user, candidate)
    redis = get_redis_client()

    try:
        # Verify session exists
        state = await _get_session_state(redis, request.session_id)
        if not state:
            raise HTTPException(status_code=404, detail="Session not found")

        turn_count = int(state.get("turn_count", b"0"))

        # Get started_at for video timestamp calculation
        started_at = state.get("started_at")
        if isinstance(started_at, bytes):
            started_at = started_at.decode("utf-8")

        # Get existing flags
        existing_flags_raw = await redis.hget(
            f"{CONTEXT_KEY_PREFIX}:{request.session_id}", "cheat_flags"
        )
        if existing_flags_raw:
            try:
                existing_flags = json.loads(existing_flags_raw)
            except json.JSONDecodeError:
                existing_flags = []
        else:
            existing_flags = []

        # Create all new flags and corresponding timeline notes
        new_flags = []
        new_notes = []
        flag_ids = []

        for flag_req in request.flags:
            flag_id = str(uuid.uuid4())
            recorded_at = datetime.now(UTC).isoformat()

            new_flag = {
                "id": flag_id,
                "flag_type": flag_req.flag_type,
                "severity": flag_req.severity,
                "confidence": flag_req.confidence,
                "description": flag_req.description,
                "evidence": flag_req.evidence,
                "timestamp": recorded_at,
                "turn_number": turn_count,
                "client_timestamp": flag_req.client_timestamp,
            }

            new_flags.append(new_flag)
            flag_ids.append(flag_id)
            new_notes.append(_timeline_note(new_flag, started_at))

        # Calculate new integrity score
        all_flags = existing_flags + new_flags
        integrity_score = _calculate_integrity_score(all_flags)

        # Recorded by the brain worker (in order, under the session lock)
        await _queue_flags(request.session_id, new_flags, new_notes)

        logger.info(
            f"Batch cheat flags recorded: session={request.session_id}, "
            f"count={len(new_flags)}, integrity={integrity_score:.2f}"
        )

        return BatchCheatFlagResponse(
            session_id=request.session_id,
            flags_recorded=len(new_flags),
            flag_ids=flag_ids,
            integrity_score=integrity_score,
        )

    finally:
        await redis.aclose()


@router.get("/sessions/{session_id}/status", response_model=IntegrityStatusResponse)
async def get_integrity_status(session_id: str, user: User = Depends(require_user)):
    """Get current integrity status for a session.

    Returns the current integrity score, flag counts, and recommendation.
    """
    await ensure_session_user_access(session_id, user)
    redis = get_redis_client()

    try:
        state = await _get_session_state(redis, session_id)
        if not state:
            raise HTTPException(status_code=404, detail="Session not found")

        # Parse cheat flags
        flags_raw = state.get("cheat_flags")
        if flags_raw:
            if isinstance(flags_raw, bytes):
                flags_raw = flags_raw.decode("utf-8")
            try:
                flags = json.loads(flags_raw)
            except json.JSONDecodeError:
                flags = []
        else:
            flags = []

        # Get integrity score
        integrity_score_raw = state.get("integrity_score", "1.0")
        if isinstance(integrity_score_raw, bytes):
            integrity_score_raw = integrity_score_raw.decode("utf-8")
        integrity_score = float(integrity_score_raw)

        # Count flags by type and severity
        flags_by_type: dict[str, int] = {}
        flags_by_severity: dict[str, int] = {}

        for flag in flags:
            flag_type = flag.get("flag_type", "unknown")
            severity = flag.get("severity", "medium")

            flags_by_type[flag_type] = flags_by_type.get(flag_type, 0) + 1
            flags_by_severity[severity] = flags_by_severity.get(severity, 0) + 1

        recommendation = _get_recommendation(integrity_score, flags_by_severity)

        return IntegrityStatusResponse(
            session_id=session_id,
            integrity_score=integrity_score,
            total_flags=len(flags),
            flags_by_type=flags_by_type,
            flags_by_severity=flags_by_severity,
            recommendation=recommendation,
        )

    finally:
        await redis.aclose()


@router.get("/sessions/{session_id}/report", response_model=IntegrityReportResponse)
async def get_integrity_report(session_id: str, user: User = Depends(require_user)):
    """Get full integrity report for a session.

    Returns a comprehensive report including all flags, timeline,
    and AI-generated summary.
    """
    await ensure_session_user_access(session_id, user)
    redis = get_redis_client()

    try:
        state = await _get_session_state(redis, session_id)
        if not state:
            raise HTTPException(status_code=404, detail="Session not found")

        # Parse cheat flags
        flags_raw = state.get("cheat_flags")
        if flags_raw:
            if isinstance(flags_raw, bytes):
                flags_raw = flags_raw.decode("utf-8")
            try:
                flags = json.loads(flags_raw)
            except json.JSONDecodeError:
                flags = []
        else:
            flags = []

        # Get integrity score
        integrity_score_raw = state.get("integrity_score", "1.0")
        if isinstance(integrity_score_raw, bytes):
            integrity_score_raw = integrity_score_raw.decode("utf-8")
        integrity_score = float(integrity_score_raw)

        # Count flags
        flags_by_type: dict[str, int] = {}
        flags_by_severity: dict[str, int] = {}

        for flag in flags:
            flag_type = flag.get("flag_type", "unknown")
            severity = flag.get("severity", "medium")

            flags_by_type[flag_type] = flags_by_type.get(flag_type, 0) + 1
            flags_by_severity[severity] = flags_by_severity.get(severity, 0) + 1

        # Get critical incidents
        critical_incidents = [
            flag for flag in flags if flag.get("severity") in ("high", "critical")
        ]

        # Sort timeline by timestamp
        timeline = sorted(flags, key=lambda f: f.get("timestamp", ""))

        # Get recommendation
        recommendation = _get_recommendation(integrity_score, flags_by_severity)

        # Generate summary
        summary = _generate_summary(
            flags, integrity_score, flags_by_type, recommendation
        )

        return IntegrityReportResponse(
            session_id=session_id,
            integrity_score=integrity_score,
            total_flags=len(flags),
            flags_by_type=flags_by_type,
            flags_by_severity=flags_by_severity,
            critical_incidents=critical_incidents,
            timeline=timeline,
            recommendation=recommendation,
            summary=summary,
        )

    finally:
        await redis.aclose()


def _generate_summary(
    flags: list[dict],
    integrity_score: float,
    flags_by_type: dict[str, int],
    recommendation: str,
) -> str:
    """Generate a human-readable summary of integrity concerns."""
    if not flags:
        return "No integrity issues detected during the interview."

    parts = []

    # Overall assessment
    if integrity_score >= 0.9:
        parts.append("Minor integrity concerns were detected during the interview.")
    elif integrity_score >= 0.7:
        parts.append("Moderate integrity concerns were detected during the interview.")
    elif integrity_score >= 0.5:
        parts.append(
            "Significant integrity concerns were detected during the interview."
        )
    else:
        parts.append(
            "Critical integrity violations were detected during the interview."
        )

    # Specific issues
    issues = []
    if flags_by_type.get("multiple_faces", 0) > 0:
        count = flags_by_type["multiple_faces"]
        issues.append(f"multiple faces detected {count} time(s)")
    if flags_by_type.get("phone_detected", 0) > 0:
        count = flags_by_type["phone_detected"]
        issues.append(f"mobile phone visible {count} time(s)")
    if flags_by_type.get("earphone_detected", 0) > 0:
        count = flags_by_type["earphone_detected"]
        issues.append(f"earphone/earbud detected {count} time(s)")
    if flags_by_type.get("tab_switch", 0) > 0:
        count = flags_by_type["tab_switch"]
        issues.append(f"browser tab switched {count} time(s)")
    if flags_by_type.get("ai_assistance", 0) > 0:
        count = flags_by_type["ai_assistance"]
        issues.append(f"suspected AI assistance {count} time(s)")

    if issues:
        parts.append(f"Issues include: {', '.join(issues)}.")

    # Recommendation
    if recommendation == "proceed":
        parts.append("Recommendation: Proceed with candidate evaluation.")
    elif recommendation == "review":
        parts.append("Recommendation: Human review of flagged incidents advised.")
    elif recommendation == "flag":
        parts.append(
            "Recommendation: Interview integrity may be compromised. "
            "Detailed review required."
        )
    else:
        parts.append(
            "Recommendation: Significant integrity violations. "
            "Consider interview invalid."
        )

    return " ".join(parts)
