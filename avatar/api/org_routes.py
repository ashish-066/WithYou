"""Organization workspace API (/org/*).

Everything here is scoped to the signed-in user's own organization, platform
admins included: the platform console has its own routes. Other organizations'
records answer 404, so their existence isn't revealed.
"""

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any, Literal

from alex_db import Interview, Invite, JobRole, session_scope
from alex_db import User as UserRow
from alex_db.audit import record
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from api.auth_routes import _public_user
from core.auth import (
    AuthStore,
    User,
    ensure_session_user_access,
    generate_password,
    invite_is_expired,
    make_invite_token,
    require_org_admin,
    require_user,
)
from core.rate_limit import client_ip
from core.recordings import get_evidence, signed_url
from core.redis import get_redis_client
from services.streams import AvatarStreamManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/org", tags=["Organization"])

CONTEXT_KEY_PREFIX = "context"
TRANSCRIPT_KEY_PREFIX = "transcript"  # full conversation, written by the worker
# Upper bound on one listing; paging moves server-side once an org gets near it
MAX_INTERVIEWS = 1000


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat() if value else None


def _number(value: str | None) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None


# =============================================================================
# Interviews
# =============================================================================


async def _live_state(session_ids: list[str]) -> dict[str, dict]:
    """Live fields from Redis for interviews that haven't ended (the worker owns that state)."""
    if not session_ids:
        return {}
    fields = ("turn_count", "max_turns", "last_updated", "started_at", "integrity_score", "interview_ended")
    redis = get_redis_client()
    try:
        pipe = redis.pipeline()
        for sid in session_ids:
            pipe.hmget(f"{CONTEXT_KEY_PREFIX}:{sid}", *fields)
        rows = await pipe.execute()
    finally:
        await redis.aclose()
    return {sid: dict(zip(fields, row, strict=True)) for sid, row in zip(session_ids, rows, strict=True) if any(row)}


def _status(interview: Interview, live: dict | None) -> str:
    """in_progress | completed. Postgres knows once it ended; Redis knows sooner."""
    if interview.status == "ended" or interview.ended_at is not None:
        return "completed"
    if live and str(live.get("interview_ended", "")).lower() in ("true", "1"):
        return "completed"
    return "in_progress"


@router.get("/interviews")
async def list_interviews(user: User = Depends(require_user)) -> dict:
    """Every interview of the organization, newest first, from Postgres.

    Finished interviews stay listed after their Redis state expires; running ones
    get live progress (turns, integrity, last activity) from Redis.
    """
    async with session_scope() as db:
        rows = (
            await db.execute(
                select(Interview, Invite.candidate_email, Invite.role_title, JobRole.role_title)
                .outerjoin(Invite, Invite.id == Interview.invite_id)
                .outerjoin(JobRole, JobRole.id == Interview.role_id)
                .where(Interview.org_id == user.org_id)
                .order_by(Interview.created_at.desc())
                .limit(MAX_INTERVIEWS)
            )
        ).all()

    running = [i.session_id for i, *_ in rows if i.status != "ended" and i.ended_at is None]
    live = await _live_state(running)

    interviews = []
    for interview, email, invite_role_title, role_title in rows:
        state = live.get(interview.session_id)
        scores = interview.scores or {}
        integrity = _number(state.get("integrity_score")) if state else scores.get("integrity_score")
        interviews.append(
            {
                "session_id": interview.session_id,
                "candidate_name": interview.candidate_name or "",
                "candidate_email": email or "",
                "role_id": interview.role_id or "",
                # The invite keeps the title it was sent with, even if the role was renamed or deleted
                "role_title": invite_role_title or role_title or "",
                "interview_mode": interview.interview_mode or "round1",
                "status": _status(interview, state),
                "end_reason": interview.end_reason or "",
                "created_at": _iso(interview.created_at),
                "ended_at": _iso(interview.ended_at),
                "last_activity": (state or {}).get("last_updated") or _iso(interview.ended_at or interview.created_at),
                "turn_count": int(_number((state or {}).get("turn_count")) or scores.get("turn_count") or 0),
                "max_turns": int(_number((state or {}).get("max_turns")) or 20),
                "integrity_score": integrity,
                "has_report": interview.report_saved_at is not None,
            }
        )
    return {"interviews": interviews, "total": len(interviews), "truncated": len(interviews) >= MAX_INTERVIEWS}


def _parse_state(data: dict[str, str]) -> dict[str, Any]:
    """The worker's context hash as plain values (JSON fields parsed)."""
    state: dict[str, Any] = {}
    for key, value in data.items():
        if value and value[0] in "[{":
            try:
                state[key] = json.loads(value)
                continue
            except ValueError:
                pass
        if key in ("turn_count", "max_turns"):
            state[key] = int(_number(value) or 0)
        elif key in ("trust_score", "integrity_score"):
            state[key] = _number(value)
        elif key == "interview_ended":
            state[key] = str(value).lower() in ("1", "true")
        else:
            state[key] = value
    return state


async def _redis_detail(session_id: str) -> tuple[dict[str, Any] | None, list[dict] | None]:
    """Live state and full transcript from Redis (either may be missing)."""
    redis = get_redis_client()
    try:
        raw = await redis.hgetall(f"{CONTEXT_KEY_PREFIX}:{session_id}")
        lines = await redis.lrange(f"{TRANSCRIPT_KEY_PREFIX}:{session_id}", 0, -1)
    finally:
        await redis.aclose()
    transcript = []
    for line in lines:
        try:
            transcript.append(json.loads(line))
        except ValueError:
            continue
    return (_parse_state(raw) if raw else None), (transcript or None)


# End reasons for interviews that ended before a proper assessment
INCOMPLETE_REASONS = {"no_response", "left_view", "disconnected", "abandoned"}


def _completion(scores: dict, state: dict) -> dict | None:
    """Saved summary once ended; live counts while running."""
    if scores.get("completion"):
        return scores["completion"]
    flow = state.get("flow") or {}
    if not flow:
        return None
    return {
        "end_reason": None,
        "incomplete": False,
        "minutes": None,
        "wrap_up_reason": flow.get("wrap_up_reason"),
        "unanswered_questions": flow.get("unanswered_total") or 0,
        "absences": flow.get("absences") or 0,
        "skills_not_assessed": [],
        "median_response_ms": None,
    }


def _decision(interview: Interview, decider: UserRow | None) -> dict | None:
    if not interview.decision:
        return None
    return {
        "decision": interview.decision,
        "note": interview.decision_note or "",
        "decided_at": _iso(interview.decided_at),
        "decided_by": (
            {"user_id": decider.id, "name": decider.name, "email": decider.email}
            if decider else None
        ),
    }


@router.get("/interviews/{session_id}")
async def get_interview_detail(session_id: str, user: User = Depends(require_user)) -> dict:
    """One interview for the report page.

    Running interviews come from the worker's live state in Redis; once ended,
    from Postgres (Redis fills anything not saved yet). Own organization only;
    platform admins may read any, but decide only for their own.
    """
    await ensure_session_user_access(session_id, user)
    async with session_scope() as db:
        row = (
            await db.execute(
                select(Interview, Invite.candidate_email, Invite.role_title, JobRole.role_title, UserRow)
                .outerjoin(Invite, Invite.id == Interview.invite_id)
                .outerjoin(JobRole, JobRole.id == Interview.role_id)
                .outerjoin(UserRow, UserRow.id == Interview.decided_by)
                .where(Interview.session_id == session_id)
            )
        ).first()
    state, live_transcript = await _redis_detail(session_id)
    if row is None and state is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if row is None:  # ownerless session that only lives in Redis (platform admins only)
        interview = Interview(session_id=session_id, status="created")
        email = invite_role_title = role_title = decider = None
    else:
        interview, email, invite_role_title, role_title, decider = row
    state = state or {}
    status = _status(interview, state)
    ended = interview.status == "ended" or interview.ended_at is not None

    def pick(saved: Any, live_key: str) -> Any:
        """Postgres once the interview ended, else (or if not saved yet) live state."""
        return saved if ended and saved is not None else state.get(live_key)

    scores = (interview.scores or {}) if ended else {}
    integrity = (interview.integrity or {}) if ended else {}
    saved_transcript = interview.transcript if ended else None
    if isinstance(saved_transcript, list):  # tolerate an older shape
        saved_transcript = {"messages": saved_transcript}
    saved_transcript = saved_transcript or {}

    report = pick(interview.report, "descriptive_report")
    if report:
        report_status = "ready"
    elif status == "completed":
        # Failed, or still nothing well after the end (the worker usually needs under a minute)
        ended_at = interview.ended_at
        overdue = ended_at is not None and (datetime.now(UTC) - ended_at).total_seconds() > REPORT_OVERDUE_SECONDS
        report_status = "failed" if state.get("report_status") == "failed" or overdue else "pending"
    else:
        report_status = "not_started"

    integrity_score = scores.get("integrity_score") if ended else None
    if integrity_score is None:
        integrity_score = state.get("integrity_score")

    detail: dict[str, Any] = {
        "session_id": session_id,
        "org_id": interview.org_id,
        "candidate_name": interview.candidate_name or state.get("candidate_name") or "",
        "candidate_email": email or "",
        "role_id": interview.role_id or state.get("role_id") or "",
        "role_title": invite_role_title or role_title or "",
        "interview_mode": interview.interview_mode or state.get("interview_mode") or "round1",
        "status": status,
        "live": status == "in_progress" and bool(state),
        "end_reason": interview.end_reason or state.get("end_reason") or "",
        "created_at": _iso(interview.created_at) if interview.created_at else None,
        "started_at": state.get("started_at") or (_iso(interview.created_at) if interview.created_at else None),
        "ended_at": _iso(interview.ended_at),
        "last_activity": state.get("last_updated") or _iso(interview.ended_at),
        "turn_count": int(scores.get("turn_count") or state.get("turn_count") or 0),
        "max_turns": int(state.get("max_turns") or 20),
        "report_status": report_status,
        "report": report,
        "analytics": pick(interview.analytics, "analytics_data"),
        "skill_tree": pick(interview.skill_tree, "skill_tree"),
        "dsa_state": pick(interview.dsa_state, "dsa_state"),
        "scores": {
            "running_scores": scores.get("running_scores") or state.get("running_scores"),
            "trust_score": scores.get("trust_score", state.get("trust_score")),
            "integrity_score": integrity_score,
            "verified_claims": scores.get("verified_claims") or state.get("verified_claims"),
        },
        # How the interview went (worker: brain/interview_flow.py)
        "completion": _completion(scores if ended else {}, state),
        "integrity": {
            "integrity_score": integrity_score,
            "cheat_flags": integrity.get("cheat_flags") or state.get("cheat_flags") or [],
            "integrity_report": integrity.get("integrity_report") or state.get("integrity_report"),
            "timestamp_notes": integrity.get("timestamp_notes") or state.get("timestamp_notes") or [],
            # Time from the end of each question to the candidate's first word
            "response_timings": integrity.get("response_timings")
            or (state.get("flow") or {}).get("response_timings")
            or [],
            # Follow-ups asked to test answers that looked looked-up
            "verification_probes": integrity.get("verification_probes")
            or (state.get("flow") or {}).get("verification_probes")
            or [],
        },
        "transcript": {
            # The worker keeps the full conversation; the state only its last messages
            "messages": saved_transcript.get("messages") or live_transcript or state.get("messages") or [],
            "summary": saved_transcript.get("summary") or state.get("message_summary"),
        },
        "recording": {
            "status": interview.recording_status or "",
            "url": signed_url(interview.recording_key) if interview.recording_key else None,
        },
        "decision": _decision(interview, decider),
        "can_decide": interview.org_id is not None and interview.org_id == user.org_id,
    }
    if user.is_platform_admin:
        # Raw records for debugging: the worker's live state, and what Postgres stored
        detail["internals"] = {
            "live_state": state or None,
            "stored": None if row is None else {
                "status": interview.status,
                "end_reason": interview.end_reason,
                "invite_id": interview.invite_id,
                "dsa_problem_id": interview.dsa_problem_id,
                "recording_key": interview.recording_key,
                "recording_status": interview.recording_status,
                "egress_id": interview.egress_id,
                "report_saved_at": _iso(interview.report_saved_at),
                "scores": interview.scores,
                "analytics": interview.analytics,
                "skill_tree": interview.skill_tree,
                "dsa_state": interview.dsa_state,
                "integrity": interview.integrity,
            },
        }
    return detail


@router.get("/interviews/{session_id}/evidence/{flag_id}")
async def evidence_photo(session_id: str, flag_id: str, request: Request, user: User = Depends(require_user)) -> Response:
    """The photo a camera-check flag was raised on (phone, another person, laptop).

    Same access as the interview; every view is audited. Never cached.
    """
    await ensure_session_user_access(session_id, user)
    async with session_scope() as db:
        interview = await db.get(Interview, session_id)
    flags = ((interview.integrity or {}) if interview else {}).get("cheat_flags") or []
    if not flags:
        state, _ = await _redis_detail(session_id)
        flags = (state or {}).get("cheat_flags") or []
    flag = next((f for f in flags if isinstance(f, dict) and f.get("id") == flag_id), None)
    key = ((flag or {}).get("evidence") or {}).get("photo_key") if isinstance((flag or {}).get("evidence"), dict) else None
    if not key or not key.startswith(f"evidence/{session_id}/"):
        raise HTTPException(status_code=404, detail="No photo for this flag")
    photo = await asyncio.to_thread(get_evidence, key)
    if photo is None:
        raise HTTPException(status_code=404, detail="Photo not available")
    await record(
        "evidence.view", actor_type="user", actor_id=user.user_id, org_id=interview.org_id if interview else None,
        target_type="interview", target_id=session_id, ip=client_ip(request), details={"flag_id": flag_id},
    )
    return Response(content=photo, media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})


REPORT_OVERDUE_SECONDS = 10 * 60


@router.post("/interviews/{session_id}/report/retry")
async def retry_report(session_id: str, user: User = Depends(require_user)) -> dict:
    """Write the report again for an ended interview that has none."""
    async with session_scope() as db:
        interview = await db.get(Interview, session_id)
    if interview is None or interview.org_id is None or interview.org_id != user.org_id:
        if interview is not None and user.can_access_org(interview.org_id):
            raise HTTPException(status_code=403, detail="Only the interview's organization can do this")
        raise HTTPException(status_code=404, detail="Session not found")
    if interview.status != "ended" and interview.ended_at is None:
        raise HTTPException(status_code=409, detail="The interview hasn't ended yet")
    if interview.report:
        raise HTTPException(status_code=409, detail="The report is already written")
    redis = get_redis_client()
    try:
        await AvatarStreamManager(redis).publish_transcription(
            session_id=session_id, content="", message_type="regenerate_report"
        )
        # Until the worker finishes, the page shows "being written" again
        await redis.hset(f"{CONTEXT_KEY_PREFIX}:{session_id}", "report_status", "pending")
    finally:
        await redis.aclose()
    await record(
        "interview.report_retry", actor_type="user", actor_id=user.user_id, org_id=user.org_id,
        target_type="interview", target_id=session_id,
    )
    return {"session_id": session_id, "queued": True}


class DecisionBody(BaseModel):
    decision: Literal["advance", "hold", "reject"] | None
    note: str = Field(default="", max_length=4000)


@router.put("/interviews/{session_id}/decision")
async def set_decision(session_id: str, body: DecisionBody, user: User = Depends(require_user)) -> dict:
    """Record (or clear, with decision null) the organization's hiring decision."""
    now = datetime.now(UTC)
    async with session_scope() as db:
        interview = await db.get(Interview, session_id, with_for_update=True)
        if interview is None or interview.org_id is None or interview.org_id != user.org_id:
            # Platform admins can read other organizations' interviews, not decide
            if interview is not None and user.can_access_org(interview.org_id):
                raise HTTPException(status_code=403, detail="Only the interview's organization can decide")
            raise HTTPException(status_code=404, detail="Session not found")
        previous = interview.decision
        interview.decision = body.decision
        interview.decision_note = (body.note.strip() or None) if body.decision else None
        interview.decided_by = user.user_id if body.decision else None
        interview.decided_at = now if body.decision else None
        decider = await db.get(UserRow, user.user_id) if body.decision else None
        result = _decision(interview, decider)
    await record(
        "interview.decision", actor_type="user", actor_id=user.user_id, org_id=user.org_id,
        target_type="interview", target_id=session_id,
        details={"decision": body.decision, "previous": previous, "note": body.note.strip() or None},
    )
    return {"session_id": session_id, "decision": result}


# =============================================================================
# Invites
# =============================================================================


async def _own_invite(invite_id: str, user: User) -> dict:
    invite = await AuthStore().get_invite(invite_id)
    if invite is None or invite["org_id"] != user.org_id:
        raise HTTPException(status_code=404, detail="Invite not found")
    return invite


@router.post("/invites/{invite_id}/revoke")
async def revoke_invite(invite_id: str, user: User = Depends(require_user)) -> dict:
    """Withdraw an invite that hasn't been used. The link stops working at once."""
    await _own_invite(invite_id, user)
    if not await AuthStore().revoke_invite(invite_id, user.org_id):
        raise HTTPException(status_code=409, detail="This invite was already used or withdrawn")
    await record(
        "invite.revoke", actor_type="user", actor_id=user.user_id, org_id=user.org_id,
        target_type="invite", target_id=invite_id,
    )
    return {"invite_id": invite_id, "status": "revoked"}


@router.post("/invites/{invite_id}/link")
async def invite_link(invite_id: str, user: User = Depends(require_user)) -> dict:
    """The link for a pending invite again (it is shown only once when created).

    Same invite, fresh token that expires with the invite: still single use.
    """
    invite = await _own_invite(invite_id, user)
    if invite["used_session_id"] or invite.get("revoked_at") or invite_is_expired(invite):
        raise HTTPException(status_code=409, detail="Only waiting invites have a link")
    remaining = datetime.fromisoformat(invite["expires_at"]) - datetime.now(UTC)
    token = make_invite_token(invite_id, remaining)
    await record(
        "invite.link_copied", actor_type="user", actor_id=user.user_id, org_id=user.org_id,
        target_type="invite", target_id=invite_id,
    )
    return {"path": f"/interview?invite={token}", "expires_at": invite["expires_at"]}


# =============================================================================
# Team
# =============================================================================


class RoleChange(BaseModel):
    role: Literal["admin", "recruiter"]


def _not_self(user_id: str, user: User, action: str) -> None:
    if user_id == user.user_id:
        raise HTTPException(status_code=400, detail=f"You can’t {action} your own account here")


@router.patch("/users/{user_id}")
async def change_role(user_id: str, body: RoleChange, user: User = Depends(require_org_admin)) -> dict:
    _not_self(user_id, user, "change the access of")
    try:
        changed = await AuthStore().set_role(user_id, user.org_id, body.role)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    if changed is None:
        raise HTTPException(status_code=404, detail="Member not found")
    await record(
        "user.role_change", actor_type="user", actor_id=user.user_id, org_id=user.org_id,
        target_type="user", target_id=user_id, details={"role": body.role},
    )
    return _public_user(changed)


@router.post("/users/{user_id}/reset-password")
async def reset_password(user_id: str, user: User = Depends(require_org_admin)) -> dict:
    """New one-time password, returned once. The member's old password stops working."""
    _not_self(user_id, user, "reset the password of")
    password = generate_password()
    if not await AuthStore().set_password(user_id, user.org_id, password):
        raise HTTPException(status_code=404, detail="Member not found")
    await record(
        "user.password_reset", actor_type="user", actor_id=user.user_id, org_id=user.org_id,
        target_type="user", target_id=user_id,
    )
    return {"user_id": user_id, "one_time_password": password}


@router.delete("/users/{user_id}")
async def remove_member(user_id: str, user: User = Depends(require_org_admin)) -> dict:
    _not_self(user_id, user, "remove")
    try:
        removed = await AuthStore().remove_user(user_id, user.org_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    if not removed:
        raise HTTPException(status_code=404, detail="Member not found")
    await record(
        "user.remove", actor_type="user", actor_id=user.user_id, org_id=user.org_id,
        target_type="user", target_id=user_id,
    )
    return {"user_id": user_id, "removed": True}
