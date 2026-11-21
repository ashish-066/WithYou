"""Durable interview outcomes in Postgres.

Redis holds the live interview context; once an interview has ended, its
outcome is copied to the interviews table so it survives Redis data loss and
can expire from Redis later.
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any

from alex_db import Interview, session_scope
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert

import core.db  # noqa: F401  (configures the database)
from brain.interview_flow import completion_summary

logger = logging.getLogger(__name__)


def _jsonable(value: Any) -> Any:
    """Plain JSON (state may hold pydantic models / datetimes before serialization)."""
    if value is None:
        return None
    return json.loads(json.dumps(value, default=str))


def outcome_from_state(
    state: dict[str, Any], transcript: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Postgres columns for an ended interview. `transcript` is the full
    conversation (services.transcript); without it, the state's recent messages."""
    return {
        "status": "ended",
        "end_reason": (state.get("end_reason") or None),
        "report": _jsonable(state.get("descriptive_report")),
        "analytics": _jsonable(state.get("analytics_data")),
        "scores": _jsonable(
            {
                "running_scores": state.get("running_scores"),
                "trust_score": state.get("trust_score"),
                "integrity_score": state.get("integrity_score"),
                "turn_count": state.get("turn_count"),
                "verified_claims": state.get("verified_claims"),
                # How the interview went: end reason, length, unanswered, absences
                "completion": completion_summary(state),
            }
        ),
        "skill_tree": _jsonable(state.get("skill_tree")),
        "dsa_state": _jsonable(state.get("dsa_state")),
        "integrity": _jsonable(
            {
                "cheat_flags": state.get("cheat_flags"),
                "integrity_report": state.get("integrity_report"),
                "timestamp_notes": state.get("timestamp_notes"),
                # Time from the end of each question to the candidate's first word
                "response_timings": (state.get("flow") or {}).get("response_timings") or [],
                # Follow-ups asked to test answers that looked looked-up (brain/verification_probe.py)
                "verification_probes": (state.get("flow") or {}).get("verification_probes") or [],
            }
        ),
        "transcript": _jsonable(
            {
                "messages": transcript if transcript else state.get("messages"),
                "summary": state.get("message_summary"),
            }
        ),
    }


async def save_interview_outcome(
    session_id: str,
    state: dict[str, Any],
    transcript: list[dict[str, Any]] | None = None,
) -> bool:
    """Upsert the outcome of an ended interview. Never raises; returns success."""
    now = datetime.now(UTC)
    values = outcome_from_state(state, transcript)
    try:
        async with session_scope() as db:
            stmt = insert(Interview).values(
                session_id=session_id, ended_at=now, report_saved_at=now, **values
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[Interview.session_id],
                set_={
                    **values,
                    # keep the first end time; record when the outcome was last saved
                    "ended_at": func.coalesce(Interview.ended_at, stmt.excluded.ended_at),
                    "report_saved_at": now,
                },
            )
            await db.execute(stmt)
        return True
    except Exception as e:
        # Loud: the outcome still exists in Redis and can be backfilled
        logger.error(f"FAILED to save interview outcome for {session_id} to Postgres: {e}")
        return False


async def state_from_saved(session_id: str) -> dict[str, Any] | None:
    """Enough of an ended interview's state to write its report again, from
    Postgres (for interviews whose live state is gone)."""
    async with session_scope() as db:
        row = await db.get(Interview, session_id)
    if row is None:
        return None
    scores = row.scores or {}
    integrity = row.integrity or {}
    transcript = row.transcript or {}
    if isinstance(transcript, list):
        transcript = {"messages": transcript}
    return {
        "session_id": session_id,
        "candidate_id": session_id,
        "interview_mode": row.interview_mode or "round1",
        "interview_ended": True,
        "end_reason": row.end_reason or "completed",
        "started_at": row.created_at.isoformat() if row.created_at else None,
        "messages": transcript.get("messages") or [],
        "message_summary": transcript.get("summary"),
        "running_scores": scores.get("running_scores") or {},
        "trust_score": scores.get("trust_score") or 1.0,
        "integrity_score": scores.get("integrity_score") or 1.0,
        "turn_count": scores.get("turn_count") or 0,
        "verified_claims": scores.get("verified_claims") or [],
        "skill_tree": row.skill_tree,
        "dsa_state": row.dsa_state,
        "analytics_data": row.analytics,
        "cheat_flags": integrity.get("cheat_flags") or [],
        "integrity_report": integrity.get("integrity_report"),
        "timestamp_notes": integrity.get("timestamp_notes") or [],
        "flow": {
            "response_timings": integrity.get("response_timings") or [],
            "verification_probes": integrity.get("verification_probes") or [],
        },
        "topics_covered": [],
    }
