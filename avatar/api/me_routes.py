"""The learner's own data: history, one session, suggestions, and insights.

    GET /me/sessions?lang=       recent sessions with something in them (newest first)
    GET /me/sessions/{id}?lang=  one session: recap + concepts (+ mood)
    GET /me/suggestions?lang=    what to study next, from the learner's own history
    GET /me/stats?lang=          streak, week, concepts, topics with learning level,
                                 mood over the last 14 days, a gentle summary

Built from the saved session records: the brain stores each session's recap
(`report`: summary, next time, suggested next topics, a gentle mood read) and its
understanding map (`analytics`: topic, concepts and their status). Text is shown
in `lang` (translated and cached when the session was in another language).
Only the learner's own sessions; no scores, no diagnoses.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from alex_db import Interview, session_scope
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select

from agents import language as lang_mod
from core.auth import User, require_user
from services.translate import translate, translate_many

router = APIRouter(prefix="/me", tags=["Learner"])

LOCAL = ZoneInfo("Asia/Kolkata")  # days count in the learner's local time
LANGS = ("ml-IN", "te-IN", "ta-IN", "hi-IN", "en-IN")
# Brain defaults that were never real topics
PLACEHOLDER_TOPICS = {"not chosen yet", "general", "introduction", ""}


# =============================================================================
# One saved session, cleaned up
# =============================================================================


def _messages(row: Interview) -> list[dict]:
    t = row.transcript
    msgs = t.get("messages") if isinstance(t, dict) else t
    return [m for m in (msgs or []) if isinstance(m, dict)]


def _learner_turns(row: Interview) -> int:
    return sum(1 for m in _messages(row) if m.get("role") in ("user", "human") and str(m.get("content") or "").strip())


def _mode(row: Interview) -> str:
    return "talk" if (row.interview_mode == "talk" or (row.analytics or {}).get("mode") == "talk") else "study"


def _language(row: Interview) -> str | None:
    if row.language in LANGS:
        return row.language
    for value in ((row.analytics or {}).get("language"), (row.report or {}).get("language")):
        if value in LANGS:
            return value
    # Older sessions: from the script of what was said
    text = " ".join(str(m.get("content") or "") for m in _messages(row))
    return lang_mod.language_of(text, default="en-IN") if text.strip() else None


def _topic(row: Interview) -> str | None:
    if _mode(row) == "talk":
        return None
    topic = (row.analytics or {}).get("topic") or row.topic
    return None if str(topic or "").strip().lower() in PLACEHOLDER_TOPICS else str(topic).strip()


def level_of(understood: int, total: int) -> str | None:
    """Learning level from the share of concepts understood (None without concepts)."""
    if not total:
        return None
    share = understood / total
    # Thirds: 2 of 3 concepts is confident, 1 of 3 is getting there
    return "confident" if share >= 0.66 else "getting_there" if share >= 0.33 else "just_started"


def _summary(row: Interview) -> dict:
    report = row.report or {}
    ideas = (row.analytics or {}).get("ideas") or []
    understood = sum(1 for i in ideas if i.get("status") == "understood")
    mood = report.get("mood") if isinstance(report.get("mood"), dict) else None
    return {
        "session_id": row.session_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "ended_at": row.ended_at.isoformat() if row.ended_at else None,
        "status": row.status,
        "mode": _mode(row),
        "language": _language(row),
        "topic": _topic(row),
        "title": report.get("title") or None,
        "summary": report.get("summary") or None,
        "next_time": report.get("next_time") or None,
        "ideas_total": len(ideas),
        "ideas_understood": understood,
        "level": level_of(understood, len(ideas)),
        "mood": mood,
        "self_mood": (row.analytics or {}).get("self_mood") or None,
    }


async def _localize(item: dict, target: str | None, fields=("topic", "title", "summary", "next_time")) -> dict:
    if target not in LANGS:
        return item
    values = await translate_many([item.get(f) for f in fields], target)
    return {**item, **dict(zip(fields, values, strict=True))}


def _mine(user: User):
    # Sessions this learner started (older ones without an owner: their organization)
    return or_(Interview.user_id == user.user_id, (Interview.user_id.is_(None)) & (Interview.org_id == user.org_id))


async def _rows(user: User, limit: int) -> list[Interview]:
    """Ended sessions in which the learner said something (connect tests etc. hidden)."""
    async with session_scope() as db:
        rows = await db.scalars(
            select(Interview).where(_mine(user)).order_by(Interview.created_at.desc()).limit(limit * 3)
        )
        return [r for r in rows if _learner_turns(r) > 0][:limit]


def _local_day(ts: datetime | None) -> date | None:
    if ts is None:
        return None
    return (ts if ts.tzinfo else ts.replace(tzinfo=UTC)).astimezone(LOCAL).date()


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/sessions")
async def my_sessions(
    limit: int = Query(default=30, ge=1, le=100),
    lang: str | None = Query(default=None),
    user: User = Depends(require_user),
) -> dict:
    items = [_summary(r) for r in await _rows(user, limit)]
    items = [await _localize(i, lang, ("topic", "title", "next_time")) for i in items]
    return {"sessions": items}


@router.get("/sessions/{session_id}")
async def my_session(session_id: str, lang: str | None = Query(default=None), user: User = Depends(require_user)) -> dict:
    async with session_scope() as db:
        row = await db.scalar(select(Interview).where(Interview.session_id == session_id, _mine(user)))
    if row is None:
        raise HTTPException(status_code=404, detail="Session not found")
    summary = await _localize(_summary(row), lang)
    recap = dict(row.report or {}) or None
    if recap:
        if summary["mode"] == "talk":
            recap["covered"], recap["improved"] = [], []  # nothing private on screen
        if lang in LANGS:
            for f in ("title", "summary", "next_time"):
                recap[f] = await translate(recap.get(f), lang)
    ideas = (row.analytics or {}).get("ideas") or [] if summary["mode"] == "study" else []
    if ideas and lang in LANGS:
        texts = await translate_many([i.get("text") for i in ideas], lang)
        ideas = [{**i, "text": t} for i, t in zip(ideas, texts, strict=True)]
    return {**summary, "recap": recap, "ideas": ideas}


@router.get("/suggestions")
async def my_suggestions(lang: str | None = Query(default=None), user: User = Depends(require_user)) -> dict:
    """From the learner's history: unfinished topics first, then topics the buddy
    suggested next at the end of their sessions. Empty for a new learner."""
    rows = await _rows(user, 60)
    seen: set[str] = set()
    cont: list[dict] = []
    for r in rows:
        s = _summary(r)
        if s["mode"] != "study" or not s["topic"] or s["topic"].lower() in seen:
            continue
        seen.add(s["topic"].lower())
        if s["ideas_total"] and s["ideas_understood"] < s["ideas_total"]:
            open_idea = next(
                (i.get("text") for i in (r.analytics or {}).get("ideas") or [] if i.get("status") != "understood"), None
            )
            cont.append({"topic": s["topic"], "level": s["level"], "next_concept": open_idea,
                         "ideas_understood": s["ideas_understood"], "ideas_total": s["ideas_total"]})
    nxt: list[str] = []
    for r in rows:
        if _mode(r) != "study":
            continue
        for t in (r.report or {}).get("suggested_next") or []:
            t = str(t).strip()
            if t and t.lower() not in seen and t.lower() not in {n.lower() for n in nxt}:
                nxt.append(t)
    cont, nxt = cont[:4], nxt[:6]
    if lang in LANGS:
        texts = await translate_many([c["topic"] for c in cont] + [c["next_concept"] for c in cont] + nxt, lang)
        n = len(cont)
        cont = [{**c, "topic": texts[i], "next_concept": texts[n + i]} for i, c in enumerate(cont)]
        nxt = texts[2 * n:]
    return {"continue": cont, "next_topics": nxt}


@router.get("/stats")
async def my_stats(
    user: User = Depends(require_user),
    today: date | None = None,
    lang: str | None = Query(default=None),
) -> dict:
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
    moods_by_day: dict[date, list[dict]] = {}
    crisis_recent = False
    for r in rows:
        s = _summary(r)
        understood_total += s["ideas_understood"]
        d = _local_day(r.created_at)
        if s["mood"] and d:
            moods_by_day.setdefault(d, []).append(s["mood"])
        if d and d >= today - timedelta(days=13) and (r.analytics or {}).get("crisis"):
            crisis_recent = True
        if s["mode"] == "study" and s["topic"]:
            t = topics.setdefault(s["topic"].strip().lower(), {
                "topic": s["topic"], "sessions": 0, "ideas_understood": 0, "ideas_total": 0, "last": s["created_at"],
            })
            t["sessions"] += 1
            t["ideas_understood"] = max(t["ideas_understood"], s["ideas_understood"])
            t["ideas_total"] = max(t["ideas_total"], s["ideas_total"])
    topic_list = sorted(topics.values(), key=lambda t: t["last"] or "", reverse=True)[:12]
    for t in topic_list:
        t["level"] = level_of(t["ideas_understood"], t["ideas_total"])
    if lang in LANGS:
        names = await translate_many([t["topic"] for t in topic_list], lang)
        for t, name in zip(topic_list, names, strict=True):
            t["topic"] = name

    timeline = []
    for i in range(13, -1, -1):
        d = today - timedelta(days=i)
        ms = moods_by_day.get(d) or []
        timeline.append({
            "day": d.isoformat(),
            "active": d in days,
            "mood_level": round(sum(m["level"] for m in ms) / len(ms), 1) if ms else None,
            "mood_label": ms[0]["label"] if ms else None,  # newest that day
        })

    return {
        "streak_days": streak,
        "sessions_total": len(rows),
        "sessions_this_week": sum(1 for r in rows if (_local_day(r.created_at) or date.min) >= week_start),
        "ideas_understood": understood_total,
        "topics": topic_list,
        "last_14_days": timeline,
        "mood": _mood_summary(timeline),
        "crisis_recent": crisis_recent,
    }


def _mood_summary(timeline: list[dict]) -> dict | None:
    """How the learner has been feeling lately: average, direction, most common feeling."""
    points = [t for t in timeline if t["mood_level"] is not None]
    if not points:
        return None
    levels = [p["mood_level"] for p in points]
    half = len(levels) // 2
    trend = "steady"
    if len(levels) >= 2 and half:
        early, late = sum(levels[:half]) / half, sum(levels[half:]) / (len(levels) - half)
        trend = "up" if late - early >= 0.5 else "down" if early - late >= 0.5 else "steady"
    common = Counter(p["mood_label"] for p in points if p["mood_label"]).most_common(1)
    return {
        "average": round(sum(levels) / len(levels), 1),
        "trend": trend,
        "common_label": common[0][0] if common else None,
        "days_with_mood": len(points),
    }
