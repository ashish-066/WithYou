"""Call management API routes for LiveKit video interviews.

These endpoints handle the creation and management of video interview calls
using LiveKit for WebRTC transport and BeyondPresence for avatar rendering.
"""

import json
import logging
import uuid
from datetime import UTC, datetime

from alex_db.audit import record
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field

from api.schemas import (
    CallResponse,
    CallStatusResponse,
    CreateCallRequest,
    EndCallResponse,
)
from core.auth import (
    AuthStore,
    Candidate,
    User,
    ensure_session_access,
    ensure_session_user_access,
    invite_is_expired,
    optional_candidate,
    optional_user,
    read_invite_token,
    require_signed_in,
    require_user,
    set_candidate_cookie,
)
from core.config import settings
from core.interviews import get_interview, update_interview
from core.rate_limit import client_ip, rate_limit
from core.recordings import SIGNED_URL_TTL_SECONDS, recording_key, signed_url
from core.redis import get_redis_client
from core.roles import get_role
from services import active_calls
from services.call_finisher import finish_call
from services.livekit_service import livekit_service
from services.presence import code_activity_key, now_iso
from services.streams import AvatarStreamManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/calls", tags=["calls"])

# Redis key pattern for job roles (matching role_routes.py)
ROLE_KEY_PREFIX = "job_role"

# Largest accepted candidate submission (characters)
MAX_CODE_CHARS = 50_000

# Live calls are tracked in Redis (services/active_calls.py) so they survive
# API restarts and are shared by every API instance.


@router.post(
    "/",
    response_model=CallResponse,
    dependencies=[Depends(rate_limit("create_call", 20, 600))],
)
async def create_call(
    request: CreateCallRequest,
    response: Response,
    user: User | None = Depends(optional_user),
    candidate: Candidate | None = Depends(optional_candidate),
    desktop_app: str | None = Header(default=None, alias="X-Presence-Desktop"),
) -> CallResponse:
    """Create a new video interview call.

    This endpoint:
    1. Checks the caller: a valid, unused invite (candidates) or a signed-in
       recruiter (trying an interview without an invite)
    2. Creates a LiveKit room for the interview
    3. Generates a participant token for the candidate
    4. Returns connection details for the frontend

    The LiveKit agent server will automatically dispatch an agent
    to the room when the candidate joins.
    """
    store = AuthStore()
    invite: dict | None = None
    invite_id: str | None = None

    if request.invite_token:
        invite_id = read_invite_token(request.invite_token)
        invite = await store.get_invite(invite_id) if invite_id else None
        if invite is None:
            raise HTTPException(status_code=404, detail="This interview link is not valid")
        # The desktop app sends this header. It keeps candidates out of an ordinary
        # browser, but a determined person could fake it: not a security boundary.
        if invite["require_secure_app"] and not desktop_app:
            raise HTTPException(status_code=403, detail="This interview must be taken in the Presence View app")
        if invite["used_session_id"]:
            rejoin = await _rejoin(invite, candidate)
            if rejoin is not None:
                return rejoin
            raise HTTPException(status_code=409, detail="This interview link has already been used")
        if invite.get("revoked_at"):
            raise HTTPException(status_code=410, detail="This interview link was withdrawn")
        if invite_is_expired(invite):
            raise HTTPException(status_code=410, detail="This interview link has expired")
        # The invite decides what is interviewed for and who the candidate is,
        # not the browser: background comes from the organization
        org_id = invite["org_id"]
        role_id = invite.get("role_id") or None
        interview_mode = invite.get("interview_mode") or "round1"
        dsa_problem_id = invite.get("dsa_problem_id") or None
        candidate_name = invite.get("candidate_name") or request.candidate_name
        background = await store.invite_background(invite_id)
    elif user is not None:
        # A recruiter trying an interview themselves
        org_id = user.org_id
        role_id = request.role_id
        interview_mode = request.interview_mode
        dsa_problem_id = request.dsa_problem_id
        candidate_name = request.candidate_name
        background = {
            "github_url": request.github_url,
            "linkedin_url": request.linkedin_url,
            "other_links": [],
            "resume_text": request.resume_text,
            "linkedin_text": None,
        }
    else:
        raise HTTPException(status_code=401, detail="An interview link is required")

    # Generate IDs (never taken from the client: a chosen session id could
    # inject messages into someone else's interview)
    call_id = f"call-{uuid.uuid4().hex[:12]}"
    session_id = f"session-{uuid.uuid4().hex[:12]}"
    room_name = f"interview-{session_id}"

    if invite_id is not None and not await store.consume_invite(invite_id, session_id):
        # Another tab/request used it a moment ago
        raise HTTPException(status_code=409, detail="This interview link has already been used")

    logger.info(f"Creating call {call_id} for session {session_id}")

    # Fetch job role data if role_id is provided
    job_title: str | None = None
    job_description: str | None = None

    if role_id:
        try:
            role_data = await get_role(role_id) or {}
            if role_data and invite is None and user is not None and not user.can_access_org(role_data.get("org_id")):
                role_data = {}  # another organization's role
            if role_data:
                job_title = role_data.get("role_title")
                job_description = role_data.get("job_description")
                logger.info(f"Fetched role data for {role_id}")
            else:
                logger.warning(f"Role ID '{role_id}' not found")
        except Exception as e:
            logger.warning(f"Failed to fetch role data: {e}")

    # The durable record of this interview (owner, invite, outcome later)
    await store.create_interview(
        session_id,
        org_id,
        invite_id=invite_id,
        candidate_name=candidate_name,
        role_id=role_id,
        interview_mode=interview_mode,
        dsa_problem_id=dsa_problem_id,
    )

    try:
        # Create LiveKit room
        await livekit_service.create_room(room_name)

        # Start recording
        egress_id = await livekit_service.start_recording(room_name, session_id)
        if egress_id:
            await update_interview(
                session_id,
                egress_id=egress_id,
                recording_key=recording_key(session_id, room_name),
                recording_status="recording",
            )

        # Generate participant token for the candidate
        token = livekit_service.generate_participant_token(
            room_name=room_name,
            participant_identity=f"candidate-{session_id}",
            participant_name=candidate_name,
        )

        # Track the call
        await active_calls.save({
            "call_id": call_id,
            "session_id": session_id,
            "room_name": room_name,
            "egress_id": egress_id,
            "candidate_name": candidate_name,
            "job_title": job_title,
            "org_id": org_id,
            "invite_id": invite_id,
            "interview_mode": interview_mode,
            "dsa_problem_id": dsa_problem_id,
            "livekit_url": settings.livekit_url,
            "created_at": datetime.now(UTC).isoformat(),
            "status": "created",
        })

        # Round 2 DSA: always publish dsa_init, independent of profile/JD data,
        # otherwise the session silently runs as Round 1.
        if interview_mode == "round2_dsa":
            try:
                redis = get_redis_client()
                await AvatarStreamManager(redis).publish_transcription(
                    session_id=session_id,
                    content="",
                    message_type="dsa_init",
                    extra_fields={
                        "interview_mode": "round2_dsa",
                        "problem_id": dsa_problem_id or "two_sum_001",
                    },
                )
                await redis.aclose()
                logger.info(f"Published dsa_init for session {session_id}")
            except Exception as e:
                logger.error(f"Failed to publish dsa_init for {session_id}: {e}")

        # Publish system_init message if profile data or job description exists
        if any(background.values()) or job_description:
            try:
                redis = get_redis_client()
                stream_manager = AvatarStreamManager(redis)

                # Build extra fields for the system_init message
                extra_fields: dict = {}

                # Candidate background: the worker gathers it into a profile the
                # interviewer asks about and checks claims against
                urls = {}
                if background.get("linkedin_url"):
                    urls["linkedin"] = background["linkedin_url"]
                if background.get("github_url"):
                    urls["github"] = background["github_url"]
                if background.get("other_links"):
                    urls["other"] = background["other_links"]
                if urls:
                    extra_fields["urls"] = urls
                if background.get("resume_text"):
                    extra_fields["resume_text"] = background["resume_text"]
                if background.get("linkedin_text"):
                    extra_fields["linkedin_text"] = background["linkedin_text"]

                # Add job description and role ID for skill tree scoring
                if job_description:
                    extra_fields["job_description"] = job_description
                    # Use the role_id if provided
                    if role_id:
                        extra_fields["role_id"] = role_id
                    if job_title:
                        extra_fields["role_title"] = job_title

                await stream_manager.publish_transcription(
                    session_id=session_id,
                    content="",  # No content for system init
                    message_type="system_init",
                    extra_fields=extra_fields,
                )
                logger.info(f"Published system_init for session {session_id}")

                await redis.aclose()
            except Exception as e:
                # Don't fail call creation if system_init fails
                logger.warning(f"Failed to publish system_init: {e}")


        logger.info(f"Call {call_id} created successfully")

        if invite is not None:
            # Grants this browser access to this one interview session only
            set_candidate_cookie(response, session_id, org_id)
        await record(
            "call.start",
            actor_type="candidate" if invite is not None else "user",
            actor_id=None if invite is not None else user.user_id,
            org_id=org_id, target_type="interview", target_id=session_id,
            details={"invite_id": invite_id} if invite_id else None,
        )

        return CallResponse(
            call_id=call_id,
            session_id=session_id,
            room_name=room_name,
            livekit_url=settings.livekit_url,
            livekit_token=token,
            status="created",
        )

    except Exception as e:
        logger.error(f"Failed to create call: {e}", exc_info=True)
        if invite_id is not None:
            # Nothing started: let the candidate try the same link again
            await store.release_invite(invite_id)
        raise HTTPException(
            status_code=500,
            detail="Could not start the interview. Please try again.",
        )


async def _rejoin(invite: dict, candidate: Candidate | None) -> CallResponse | None:
    """Same browser coming back to its own interview (refresh / dropped connection)."""
    session_id = invite["used_session_id"]
    if candidate is None or candidate.session_id != session_id:
        return None
    call = await active_calls.get_by_session(session_id)
    if call is None:
        return None  # interview already ended
    token = livekit_service.generate_participant_token(
        room_name=call["room_name"],
        participant_identity=f"candidate-{session_id}",
        participant_name=call.get("candidate_name"),
    )
    logger.info(f"Candidate rejoined call {call['call_id']}")
    return CallResponse(
        call_id=call["call_id"],
        session_id=session_id,
        room_name=call["room_name"],
        livekit_url=settings.livekit_url,
        livekit_token=token,
        status="rejoined",
    )


@router.get(
    "/{call_id}",
    response_model=CallStatusResponse,
    dependencies=[Depends(require_signed_in)],
)
async def get_call_status(
    call_id: str,
    user: User | None = Depends(optional_user),
    candidate: Candidate | None = Depends(optional_candidate),
) -> CallStatusResponse:
    """Get the status of an active call."""
    call = await active_calls.get(call_id)
    if call is None:
        raise HTTPException(status_code=404, detail="Call not found")
    await ensure_session_access(call["session_id"], user, candidate)

    # Try to get participant count from LiveKit
    participant_count = 0
    try:
        room = await livekit_service.get_room(call["room_name"])
        if room:
            participant_count = room.num_participants
    except Exception as e:
        logger.warning(f"Could not get room info: {e}")

    return CallStatusResponse(
        call_id=call_id,
        session_id=call["session_id"],
        status=call["status"],
        participant_count=participant_count,
        created_at=call.get("created_at"),
    )


@router.delete(
    "/{call_id}",
    response_model=EndCallResponse,
    dependencies=[Depends(require_signed_in)],
)
async def end_call(
    call_id: str,
    user: User | None = Depends(optional_user),
    candidate: Candidate | None = Depends(optional_candidate),
) -> EndCallResponse:
    """End an active call and cleanup resources.

    This endpoint:
    1. Deletes the LiveKit room (disconnecting all participants)
    2. Cleans up call tracking

    Handles duplicate requests gracefully by returning success for recently-ended calls.
    """
    # Check if this call was recently ended (handles duplicate DELETE requests)
    if await active_calls.recently_ended(call_id):
        logger.info(f"Duplicate end_call request for {call_id}, returning success")
        return EndCallResponse(
            call_id=call_id,
            status="ended",
            message="Call already ended",
        )

    call = await active_calls.get(call_id)
    if call is None:
        raise HTTPException(status_code=404, detail="Call not found")
    await ensure_session_access(call["session_id"], user, candidate)

    # Atomically take it out of the live set, so concurrent requests (even on
    # other API instances) don't both clean up
    call = await active_calls.claim_for_ending(call_id)
    if call is None:
        return EndCallResponse(call_id=call_id, status="ended", message="Call already ended")

    session_id = call["session_id"]
    logger.info(f"Ending call {call_id}")

    try:
        await finish_call(call, "user_ended", publish_end_signal=True)

        logger.info(f"Call {call_id} ended successfully")
        await record(
            "call.end",
            actor_type="candidate" if candidate is not None and user is None else "user",
            actor_id=user.user_id if user is not None else None,
            org_id=call.get("org_id"), target_type="interview", target_id=session_id,
        )

        return EndCallResponse(
            call_id=call_id,
            status="ended",
            message="Call ended successfully",
        )

    except Exception as e:
        logger.error(f"Error ending call: {e}", exc_info=True)
        # Cleanup failed: put the call back so ending can be retried
        await active_calls.forget_ended(call_id)
        await active_calls.save(call)
        raise HTTPException(
            status_code=500,
            detail="Could not end the call cleanly. Please try again.",
        )


@router.get("/recordings/{session_id}", tags=["Recordings"])
async def get_session_recording(
    session_id: str, request: Request, user: User = Depends(require_user)
):
    """Recording of a session (recruiters of the owning org only).

    Returns a signed link valid for 15 minutes; it is generated per request and
    every access is audited.
    """
    await ensure_session_user_access(session_id, user)
    interview = await get_interview(session_id)
    if interview is None or not interview.recording_key:
        raise HTTPException(status_code=404, detail="Recording not found")

    url = signed_url(interview.recording_key)
    await record(
        "recording.view", actor_type="user", actor_id=user.user_id, org_id=user.org_id,
        target_type="interview", target_id=session_id, ip=client_ip(request),
    )
    return {
        "session_id": session_id,
        "status": interview.recording_status,
        "url": url,
        "expires_in_seconds": SIGNED_URL_TTL_SECONDS if url else None,
        "created_at": interview.created_at.isoformat() if interview.created_at else None,
    }


class DSACodeRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=120)
    code: str = Field(max_length=MAX_CODE_CHARS)
    language: str = Field(default="python", max_length=20)


@router.post("/dsa/code_snapshot", tags=["DSA"], dependencies=[Depends(require_signed_in)])
async def snapshot_dsa_code(
    request: DSACodeRequest,
    user: User | None = Depends(optional_user),
    candidate: Candidate | None = Depends(optional_candidate),
) -> dict:
    """Silently record the candidate's current editor contents (no response generated)."""
    await ensure_session_access(request.session_id, user, candidate)
    if not request.code.strip():
        return {"queued": False}
    redis = get_redis_client()
    try:
        # The voice agent reads this to tell "coding quietly" from "idle"
        await redis.set(code_activity_key(request.session_id), now_iso(), ex=3600)
        await AvatarStreamManager(redis).publish_transcription(
            session_id=request.session_id,
            content="",
            message_type="dsa_code_snapshot",
            extra_fields={"code": request.code},
        )
    finally:
        await redis.aclose()
    return {"queued": True}


@router.post(
    "/dsa/execute",
    tags=["DSA"],
    dependencies=[Depends(require_signed_in), Depends(rate_limit("dsa_execute", 20, 60))],
)
async def execute_dsa_code(
    request: DSACodeRequest,
    user: User | None = Depends(optional_user),
    candidate: Candidate | None = Depends(optional_candidate),
) -> dict:
    """Submit candidate code for DSA sandbox execution.

    The frontend POSTs the code here; this endpoint publishes a
    dsa_code_execute message to the Redis stream so the worker can
    run it through the sandboxed executor and have Presence respond.

    Request body:
        session_id: str
        code: str         (Python source code, up to MAX_CODE_CHARS)
        language: str     (currently only 'python' supported)

    Returns:
        {"queued": True} if the message was published successfully.
    """
    await ensure_session_access(request.session_id, user, candidate)
    if not request.code.strip():
        raise HTTPException(status_code=400, detail="code must not be empty")
    if request.language != "python":
        raise HTTPException(status_code=400, detail="Only 'python' is supported in the current version")

    try:
        redis = get_redis_client()
        stream_manager = AvatarStreamManager(redis)
        await redis.set(code_activity_key(request.session_id), now_iso(), ex=3600)

        await stream_manager.publish_transcription(
            session_id=request.session_id,
            content="",
            message_type="dsa_code_execute",
            extra_fields={"code": request.code, "language": request.language},
        )

        await redis.aclose()
        logger.info(f"Published dsa_code_execute for session {request.session_id} ({len(request.code)} chars)")
        return {"queued": True, "session_id": request.session_id}

    except Exception as e:
        logger.error(f"Failed to publish dsa_code_execute for {request.session_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to queue code execution")


@router.get("/dsa/result/{session_id}", tags=["DSA"], dependencies=[Depends(require_signed_in)])
async def get_dsa_result(
    session_id: str,
    user: User | None = Depends(optional_user),
    candidate: Candidate | None = Depends(optional_candidate),
) -> dict:
    """Latest code execution result for the interview room.

    Candidate-safe: returns only the test-run result, never the rest of the
    session state (reference solution, scores, evaluator notes).
    """
    await ensure_session_access(session_id, user, candidate)
    redis = get_redis_client()
    raw = await redis.hget(f"{settings.context_prefix}:{session_id}", "dsa_state")
    try:
        dsa_state = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        dsa_state = {}
    dsa_state = dsa_state or {}
    # last_run includes runs that failed because the runner was unavailable
    latest = dsa_state.get("last_run") or dsa_state.get("last_execution_result")
    return {"last_execution_result": latest}
