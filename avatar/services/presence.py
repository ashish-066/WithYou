"""Coding activity the voice agent reads (agents/interview_monitor.py).

Code snapshots and runs mark the time; the agent polls it once a second to
tell "coding quietly" from "idle". Camera checks run in the agent itself, on
the candidate's video (agents/vision.py), so the candidate can't fake them.
"""

from datetime import UTC, datetime


def code_activity_key(session_id: str) -> str:
    return f"activity:code:{session_id}"


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def to_epoch(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).timestamp()
