"""Platform console API (/platform/*): platform admins only.

Everyone else gets 404, so the console's existence isn't revealed. Covers what
operating the service needs across organizations: health, organizations, every
interview, workers, queues and dead letters, and the audit log.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from alex_db import AuditEvent, Interview, Invite, JobRole, Organization, session_scope
from alex_db import User as UserRow
from alex_db.audit import record
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, text

from api.admin_routes import METRICS_KEY_PREFIX, _get_stream_stats, _get_workers
from api.org_routes import _live_state, _number, _status
from core.auth import User, require_user
from core.config import settings
from core.recordings import storage_configured
from core.redis import get_redis_client

logger = logging.getLogger(__name__)


async def require_platform(user: User = Depends(require_user)) -> User:
    if not user.is_platform_admin:
        raise HTTPException(status_code=404, detail="Not found")
    return user


router = APIRouter(prefix="/platform", tags=["Platform"], dependencies=[Depends(require_platform)])

MAX_ROWS = 1000
# A worker whose heartbeat is older than this is shown as stale (the key itself expires later)
STALE_HEARTBEAT_SECONDS = 60


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat() if value else None


def _age_seconds(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        then = datetime.fromisoformat(iso)
    except ValueError:
        return None
    if then.tzinfo is None:
        then = then.replace(tzinfo=UTC)
    return (datetime.now(UTC) - then).total_seconds()


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# =============================================================================
# Health
# =============================================================================


@router.get("/health")
async def health() -> dict:
    """One row per part of the system: ok | warn | down, with a short detail."""
    rows: list[dict[str, str]] = [{"part": "api", "state": "ok", "detail": "Answering"}]

    try:
        async with session_scope() as db:
            await db.execute(text("SELECT 1"))
        rows.append({"part": "database", "state": "ok", "detail": "Connected"})
    except Exception as e:
        logger.error(f"Health: database check failed: {e}")
        rows.append({"part": "database", "state": "down", "detail": "Not reachable"})

    redis = get_redis_client()
    try:
        await redis.ping()
        rows.append({"part": "redis", "state": "ok", "detail": "Connected"})
        workers = await _get_workers(redis)
        requests = await _get_stream_stats(redis, settings.request_stream)
        dead = await redis.xlen(settings.dead_letter_stream)
    except Exception as e:
        logger.error(f"Health: redis check failed: {e}")
        rows.append({"part": "redis", "state": "down", "detail": "Not reachable"})
        workers, requests, dead = None, None, None
    finally:
        await redis.aclose()

    if workers is not None:
        fresh = [w for w in workers if (_age_seconds(w.get("last_heartbeat")) or 1e9) < STALE_HEARTBEAT_SECONDS]
        if not workers:
            rows.append({"part": "workers", "state": "down", "detail": "No worker registered"})
        elif len(fresh) < len(workers):
            rows.append({"part": "workers", "state": "warn",
                         "detail": f"{len(fresh)} of {len(workers)} sending heartbeats"})
        else:
            rows.append({"part": "workers", "state": "ok", "detail": f"{len(workers)} running"})
    if requests is not None:
        pending = requests.pending_messages
        rows.append({
            "part": "queues",
            "state": "warn" if pending > 20 else "ok",
            "detail": f"{pending} waiting, {requests.length} in the request stream",
        })
    if dead is not None:
        rows.append({
            "part": "dead_letters",
            "state": "warn" if dead else "ok",
            "detail": f"{dead} message{'s' if dead != 1 else ''} gave up on" if dead else "None",
        })

    rows.append({
        "part": "agent",
        "state": "ok" if settings.livekit_url else "down",
        "detail": "LiveKit configured" if settings.livekit_url else "LiveKit not configured",
    })
    rows.append({
        "part": "recordings",
        "state": "ok" if storage_configured() else "warn",
        "detail": "Storage configured" if storage_configured() else "Storage not configured; nothing is recorded",
    })

    worst = "down" if any(r["state"] == "down" for r in rows) else "warn" if any(r["state"] == "warn" for r in rows) else "ok"
    return {"state": worst, "checked_at": _iso(datetime.now(UTC)), "parts": rows}


# =============================================================================
# Organizations
# =============================================================================


def _members_subquery():
    return (
        select(UserRow.org_id, func.count().label("members"))
        .group_by(UserRow.org_id)
        .subquery()
    )


def _interviews_subquery():
    return (
        select(
            Interview.org_id,
            func.count().label("interviews"),
            func.max(func.coalesce(Interview.ended_at, Interview.created_at)).label("last_active"),
        )
        .group_by(Interview.org_id)
        .subquery()
    )


@router.get("/organizations")
async def list_organizations() -> dict:
    members = _members_subquery()
    interviews = _interviews_subquery()
    async with session_scope() as db:
        rows = (
            await db.execute(
                select(Organization, members.c.members, interviews.c.interviews, interviews.c.last_active)
                .outerjoin(members, members.c.org_id == Organization.id)
                .outerjoin(interviews, interviews.c.org_id == Organization.id)
                .order_by(Organization.created_at.desc())
                .limit(MAX_ROWS)
            )
        ).all()
    return {
        "organizations": [
            {
                "org_id": org.id,
                "name": org.name,
                "members": n_members or 0,
                "interviews": n_interviews or 0,
                "last_active": _iso(last_active),
                "created_at": _iso(org.created_at),
            }
            for org, n_members, n_interviews, last_active in rows
        ]
    }


def _interview_row(interview: Interview, email: str | None, invite_role: str | None,
                   role_title: str | None, org_name: str | None, live: dict | None = None) -> dict:
    scores = interview.scores or {}
    integrity = _number(live.get("integrity_score")) if live else scores.get("integrity_score")
    return {
        "session_id": interview.session_id,
        "org_id": interview.org_id,
        "org_name": org_name or "",
        "candidate_name": interview.candidate_name or "",
        "candidate_email": email or "",
        "role_id": interview.role_id or "",
        "role_title": invite_role or role_title or "",
        "interview_mode": interview.interview_mode or "round1",
        "status": _status(interview, live),
        "end_reason": interview.end_reason or "",
        "created_at": _iso(interview.created_at),
        "ended_at": _iso(interview.ended_at),
        "last_activity": (live or {}).get("last_updated") or _iso(interview.ended_at or interview.created_at),
        "turn_count": int(_number((live or {}).get("turn_count")) or scores.get("turn_count") or 0),
        "integrity_score": integrity,
        "has_report": interview.report_saved_at is not None,
        "decision": interview.decision,
    }


async def _rows_with_live(rows) -> list[dict]:
    """Interview rows, with live fields from Redis for ones still running."""
    running = [r[0].session_id for r in rows if r[0].status != "ended" and r[0].ended_at is None]
    live = await _live_state(running)
    return [_interview_row(*r, live=live.get(r[0].session_id)) for r in rows]


def _interviews_query():
    return (
        select(Interview, Invite.candidate_email, Invite.role_title, JobRole.role_title, Organization.name)
        .outerjoin(Invite, Invite.id == Interview.invite_id)
        .outerjoin(JobRole, JobRole.id == Interview.role_id)
        .outerjoin(Organization, Organization.id == Interview.org_id)
        .order_by(Interview.created_at.desc())
    )


@router.get("/organizations/{org_id}")
async def get_organization(org_id: str) -> dict:
    members = _members_subquery()
    interviews = _interviews_subquery()
    async with session_scope() as db:
        row = (
            await db.execute(
                select(Organization, members.c.members, interviews.c.interviews, interviews.c.last_active)
                .outerjoin(members, members.c.org_id == Organization.id)
                .outerjoin(interviews, interviews.c.org_id == Organization.id)
                .where(Organization.id == org_id)
            )
        ).first()
        if row is None:
            raise HTTPException(status_code=404, detail="Organization not found")
        users = (
            await db.scalars(select(UserRow).where(UserRow.org_id == org_id).order_by(UserRow.created_at))
        ).all()
        recent = (await db.execute(_interviews_query().where(Interview.org_id == org_id).limit(50))).all()
    org, n_members, n_interviews, last_active = row
    return {
        "org_id": org.id,
        "name": org.name,
        "created_at": _iso(org.created_at),
        "members_count": n_members or 0,
        "interviews_count": n_interviews or 0,
        "last_active": _iso(last_active),
        "members": [
            {
                "user_id": u.id,
                "name": u.name,
                "email": u.email,
                "role": u.role,
                "is_platform_admin": u.is_platform_admin,
                "created_at": _iso(u.created_at),
            }
            for u in users
        ],
        "recent_interviews": await _rows_with_live(recent),
    }


# =============================================================================
# Interviews (every organization)
# =============================================================================


@router.get("/interviews")
async def list_all_interviews(include_unowned: bool = False) -> dict:
    """Every organization's interviews from Postgres, newest first.

    Sessions without an organization (scalability demo, very old sessions) are
    left out unless include_unowned is set.
    """
    query = _interviews_query().limit(MAX_ROWS)
    if not include_unowned:
        query = query.where(Interview.org_id.is_not(None))
    async with session_scope() as db:
        rows = (await db.execute(query)).all()
    interviews = await _rows_with_live(rows)
    return {"interviews": interviews, "total": len(interviews), "truncated": len(interviews) >= MAX_ROWS}


# =============================================================================
# Workers and queues
# =============================================================================


@router.get("/workers")
async def list_workers() -> dict:
    """Registered workers with their metrics, busiest state first."""
    redis = get_redis_client()
    try:
        workers = await _get_workers(redis)
        pipe = redis.pipeline()
        for w in workers:
            pipe.hgetall(f"{METRICS_KEY_PREFIX}:{w.get('worker_id', '')}")
        metrics = await pipe.execute() if workers else []
    finally:
        await redis.aclose()

    rows = []
    for w, m in zip(workers, metrics, strict=True):
        age = _age_seconds(w.get("last_heartbeat"))
        rows.append({
            "worker_id": w.get("worker_id", "unknown"),
            "hostname": w.get("hostname", ""),
            "status": w.get("status", "unknown"),
            "stale": age is None or age > STALE_HEARTBEAT_SECONDS,
            "current_session": w.get("current_session"),
            "started_at": w.get("started_at"),
            "last_heartbeat": w.get("last_heartbeat"),
            "messages_processed": int(_float(m.get("messages_processed")) or 0),
            "messages_failed": int(_float(m.get("messages_failed")) or 0),
            "avg_latency_ms": _float(m.get("avg_latency_ms")),
            "p95_latency_ms": _float(m.get("p95_latency_ms")),
        })
    rows.sort(key=lambda r: (r["stale"], r["worker_id"]))
    return {"workers": rows}


@router.get("/queues")
async def queues(limit: int = Query(100, ge=1, le=500)) -> dict:
    """Request/response stream stats and the dead letters (newest first, with payloads)."""
    redis = get_redis_client()
    try:
        request_stats = await _get_stream_stats(redis, settings.request_stream)
        response_stats = await _get_stream_stats(redis, settings.response_stream)
        entries = await redis.xrevrange(settings.dead_letter_stream, count=limit)
        dead_total = await redis.xlen(settings.dead_letter_stream)
    finally:
        await redis.aclose()
    return {
        "streams": [
            {"name": settings.request_stream, "kind": "requests", **request_stats.model_dump()},
            {"name": settings.response_stream, "kind": "responses", **response_stats.model_dump()},
        ],
        "dead_letters_total": dead_total,
        "dead_letters": [{"id": entry_id, **data} for entry_id, data in entries],
    }


# =============================================================================
# Audit log
# =============================================================================


@router.get("/audit")
async def audit_log(
    org_id: str | None = None,
    actor: str | None = Query(None, description="User id or email"),
    action: str | None = Query(None, description="Exact action, or a prefix ending in '.' (e.g. 'invite.')"),
    since: datetime | None = None,
    until: datetime | None = None,
    before_id: int | None = Query(None, description="Paging: events older than this id"),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    query = (
        select(AuditEvent, UserRow.name, UserRow.email, Organization.name)
        .outerjoin(UserRow, (AuditEvent.actor_type == "user") & (UserRow.id == AuditEvent.actor_id))
        .outerjoin(Organization, Organization.id == AuditEvent.org_id)
        .order_by(AuditEvent.id.desc())
        .limit(limit + 1)
    )
    if org_id:
        query = query.where(AuditEvent.org_id == org_id)
    if actor:
        query = query.where((AuditEvent.actor_id == actor) | (func.lower(UserRow.email) == actor.lower()))
    if action:
        query = query.where(
            AuditEvent.action.startswith(action) if action.endswith(".") else AuditEvent.action == action
        )
    if since:
        query = query.where(AuditEvent.at >= since)
    if until:
        query = query.where(AuditEvent.at < until)
    if before_id:
        query = query.where(AuditEvent.id < before_id)

    async with session_scope() as db:
        rows = (await db.execute(query)).all()
        actions = (await db.scalars(select(AuditEvent.action).distinct().order_by(AuditEvent.action))).all()

    more = len(rows) > limit
    rows = rows[:limit]
    return {
        "events": [
            {
                "id": e.id,
                "at": _iso(e.at),
                "org_id": e.org_id,
                "org_name": org_name or "",
                "actor_type": e.actor_type,
                "actor_id": e.actor_id,
                "actor_name": name or "",
                "actor_email": email or "",
                "action": e.action,
                "target_type": e.target_type,
                "target_id": e.target_id,
                "ip": e.ip,
                "details": e.details,
            }
            for e, name, email, org_name in rows
        ],
        "next_before_id": rows[-1][0].id if more and rows else None,
        "actions": list(actions),
    }


# =============================================================================
# Coding problem library
# =============================================================================


def _problem_models():
    """DSA models live in worker/; dsa_routes imports them once at startup."""
    from api import dsa_routes

    dsa_routes._require_dsa()
    return dsa_routes._DSAProblem, dsa_routes._DSAProblemStore


def _validate_problem(data: dict) -> Any:
    model, _ = _problem_models()
    try:
        problem = model.model_validate(data)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"The problem isn’t valid: {e}") from e
    if problem.scoring_rubric.dimensions and not problem.scoring_rubric.validate_weights():
        total = sum(d.weight for d in problem.scoring_rubric.dimensions)
        raise HTTPException(status_code=422, detail=f"Rubric weights must add up to 100% (now {total * 100:.0f}%)")
    if not problem.public_test_cases and not problem.hidden_test_cases:
        raise HTTPException(status_code=422, detail="Add at least one test")
    return problem


async def _problem_usage() -> dict[str, dict[str, int]]:
    """How many invites and interviews use each problem."""
    async with session_scope() as db:
        invites = (await db.execute(
            select(Invite.dsa_problem_id, func.count()).where(Invite.dsa_problem_id.is_not(None))
            .group_by(Invite.dsa_problem_id)
        )).all()
        interviews = (await db.execute(
            select(Interview.dsa_problem_id, func.count()).where(Interview.dsa_problem_id.is_not(None))
            .group_by(Interview.dsa_problem_id)
        )).all()
    usage: dict[str, dict[str, int]] = {}
    for pid, n in invites:
        usage.setdefault(pid, {"invites": 0, "interviews": 0})["invites"] = n
    for pid, n in interviews:
        usage.setdefault(pid, {"invites": 0, "interviews": 0})["interviews"] = n
    return usage


@router.get("/problems")
async def list_problems() -> dict:
    _, store_cls = _problem_models()
    redis = get_redis_client()
    try:
        store = store_cls(redis)
        problems = await store.list_all()
        # Test counts need the full record; the library is small (tens of problems)
        full = {p["problem_id"]: await store.get(p["problem_id"]) for p in problems}
    finally:
        await redis.aclose()
    usage = await _problem_usage()
    rows = []
    for p in problems:
        f = full.get(p["problem_id"])
        rows.append({
            **p,
            "public_tests": len(f.public_test_cases) if f else 0,
            "hidden_tests": len(f.hidden_test_cases) if f else 0,
            "hints": len(f.hint_policy.hints) if f else 0,
            **usage.get(p["problem_id"], {"invites": 0, "interviews": 0}),
        })
    return {"problems": rows}


@router.get("/problems/{problem_id}")
async def get_problem(problem_id: str) -> dict:
    _, store_cls = _problem_models()
    redis = get_redis_client()
    try:
        problem = await store_cls(redis).get(problem_id)
    finally:
        await redis.aclose()
    if problem is None:
        raise HTTPException(status_code=404, detail="Problem not found")
    return {"problem": problem.model_dump(), "usage": (await _problem_usage()).get(problem_id, {"invites": 0, "interviews": 0})}


@router.post("/problems", status_code=201)
async def create_problem(body: dict, user: User = Depends(require_platform)) -> dict:
    problem = _validate_problem({**body, "created_by": user.email})
    _, store_cls = _problem_models()
    redis = get_redis_client()
    try:
        try:
            created = await store_cls(redis).create(problem)
        except ValueError as e:
            raise HTTPException(status_code=409, detail=f"A problem with the id “{problem.problem_id}” already exists") from e
    finally:
        await redis.aclose()
    await _audit_problem("problem.create", user, problem.problem_id)
    return {"problem": created.model_dump()}


@router.put("/problems/{problem_id}")
async def update_problem(problem_id: str, body: dict, user: User = Depends(require_platform)) -> dict:
    problem = _validate_problem({**body, "problem_id": problem_id})
    _, store_cls = _problem_models()
    redis = get_redis_client()
    try:
        try:
            updated = await store_cls(redis).update(problem)
        except ValueError as e:
            raise HTTPException(status_code=404, detail="Problem not found") from e
    finally:
        await redis.aclose()
    await _audit_problem("problem.update", user, problem_id)
    return {"problem": updated.model_dump()}


@router.delete("/problems/{problem_id}")
async def delete_problem(problem_id: str, user: User = Depends(require_platform)) -> dict:
    """Delete a problem. Finished interviews keep their results; waiting invites
    for it can no longer start a coding round, so they're reported back."""
    _, store_cls = _problem_models()
    redis = get_redis_client()
    try:
        deleted = await store_cls(redis).delete(problem_id)
    finally:
        await redis.aclose()
    if not deleted:
        raise HTTPException(status_code=404, detail="Problem not found")
    await _audit_problem("problem.delete", user, problem_id)
    return {"problem_id": problem_id, "deleted": True}


async def _audit_problem(action: str, user: User, problem_id: str) -> None:
    await record(action, actor_type="user", actor_id=user.user_id, org_id=user.org_id,
                 target_type="problem", target_id=problem_id)
