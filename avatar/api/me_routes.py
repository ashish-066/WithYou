"""The learner's own data: past sessions, one session's recap, and progress.

    GET /me/sessions            recent sessions (newest first)
    GET /me/sessions/{id}       one session: recap card + key ideas
    GET /me/stats               streak, this week, ideas understood, topics, last 14 days

Built from the saved session records (Postgres): the brain stores each session's
recap (`report`) and understanding map summary (`analytics`) when it ends.
Only the learner's own sessions; no scores anywhere.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from alex_db import Interview, session_scope
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select

from core.auth import User, require_user

router = APIRouter(prefix="/me", tags=["Learner"])

# Days count in the learner's local time (the app is for learners in India)
LOCAL = ZoneInfo("Asia/Kolkata")


def _mode(row: Interview) -> str:
    return "talk" if row.interview_mode == "talk" else "study"


def _summary(row: Interview) -> dict:
    report = row.report or {}
    analytics = row.analytics or {}
    ideas = analytics.get("ideas") or []
    return {
        "session_id": row.session_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "ended_at": row.ended_at.isoformat() if row.ended_at else None,
        "status": row.status,
        "mode": _mode(row),
        "language": row.language or analytics.get("language") or report.get("language"),
        "topic": analytics.get("topic") or row.topic,
        "title": report.get("title") or None,
        "summary": report.get("summary") or None,
        "next_time": report.get("next_time") or None,
        "ideas_total": len(ideas),
        "ideas_understood": sum(1 for i in ideas if i.get("status") == "understood"),
    }


def _mine(user: User):
    # Sessions started by this learner (older ones without an owner: their organization)
    return or_(Interview.user_id == user.user_id, (Interview.user_id.is_(None)) & (Interview.org_id == user.org_id))


async def _rows(user: User, limit: int) -> list[Interview]:
    async with session_scope() as db:
        rows = await db.scalars(
            select(Interview).where(_mine(user)).order_by(Interview.created_at.desc()).limit(limit)
        )
        return list(rows)


@router.get("/sessions")
async def my_sessions(limit: int = Query(default=30, ge=1, le=100), user: User = Depends(require_user)) -> dict:
    return {"sessions": [_summary(r) for r in await _rows(user, limit)]}


@router.get("/sessions/{session_id}")
async def my_session(session_id: str, user: User = Depends(require_user)) -> dict:
    async with session_scope() as db:
        row = await db.scalar(select(Interview).where(Interview.session_id == session_id, _mine(user)))
    if row is None:
        raise HTTPException(status_code=404, detail="Session not found")
    summary = _summary(row)
    recap = row.report or None
    if summary["mode"] == "talk" and recap:
        recap = {**recap, "covered": [], "improved": []}  # nothing private on screen
    ideas = (row.analytics or {}).get("ideas") or []
    return {**summary, "recap": recap, "ideas": ideas if summary["mode"] == "study" else []}


def _local_day(ts: datetime | None) -> date | None:
    if ts is None:
        return None
    return (ts if ts.tzinfo else ts.replace(tzinfo=UTC)).astimezone(LOCAL).date()


@router.get("/stats")
async def my_stats(user: User = Depends(require_user), today: date | None = None) -> dict:
    rows = await _rows(user, 1000)
    today = today or datetime.now(LOCAL).date()
    days = {d for d in (_local_day(r.created_at) for r in rows) if d}

    # Streak: consecutive days with a session, ending today (or yesterday, if not yet today)
    streak, day = 0, today if today in days else today - timedelta(days=1)
    while day in days:
        streak += 1
        day -= timedelta(days=1)

    week_start = today - timedelta(days=6)
    topics: dict[str, dict] = {}
    understood_total = 0
    for r in rows:
        s = _summary(r)
        understood_total += s["ideas_understood"]
        if s["mode"] == "study" and s["topic"]:
            t = topics.setdefault(s["topic"].strip().lower(), {
                "topic": s["topic"], "sessions": 0, "ideas_understood": 0, "ideas_total": 0, "last": s["created_at"],
            })
            t["sessions"] += 1
            t["ideas_understood"] = max(t["ideas_understood"], s["ideas_understood"])
            t["ideas_total"] = max(t["ideas_total"], s["ideas_total"])

    return {
        "streak_days": streak,
        "sessions_total": len(rows),
        "sessions_this_week": sum(1 for r in rows if (_local_day(r.created_at) or date.min) >= week_start),
        "ideas_understood": understood_total,
        "topics": sorted(topics.values(), key=lambda t: t["last"] or "", reverse=True)[:12],
        "last_14_days": [
            {"day": (today - timedelta(days=i)).isoformat(), "active": (today - timedelta(days=i)) in days}
            for i in range(13, -1, -1)
        ],
    }
