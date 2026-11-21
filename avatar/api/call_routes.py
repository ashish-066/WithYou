"""Call management API routes for LiveKit study sessions.

A signed-in learner starts a call; the voice agent joins the LiveKit room and
relays turns to the brain worker over Redis.
"""

import logging
import uuid
from datetime import UTC, datetime

from alex_db.audit import record
from fastapi import APIRouter, Depends, HTTPException

from api.schemas import (
    CallResponse,
    CallStatusResponse,
    CreateCallRequest,
    EndCallResponse,
)
from core.auth import AuthStore, User, ensure_session_user_access, require_user
from core.config import settings
from core.rate_limit import rate_limit
from core.redis import get_redis_client
from services import active_calls
from services.call_finisher import finish_call
from services.livekit_service import livekit_service
from services.streams import AvatarStreamManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/calls", tags=["calls"])

# Live calls are tracked in Redis (services/active_calls.py) so they survive
# API restarts and are shared by every API instance.


@router.post(
    "/",
    response_model=CallResponse,
    dependencies=[Depends(rate_limit("create_call", 20, 600))],
)
async def create_call(request: CreateCallRequest, user: User = Depends(require_user)) -> CallResponse:
    """Start a study session: create the LiveKit room and a token for the learner.

    The LiveKit agent server dispatches the voice agent when the learner joins.
    """
    # Generated here, never taken from the client: a chosen session id could
    # inject messages into someone else's session
    call_id = f"call-{uuid.uuid4().hex[:12]}"
    session_id = f"session-{uuid.uuid4().hex[:12]}"
    room_name = f"interview-{session_id}"
    name = request.candidate_name

    logger.info(f"Creating call {call_id} for session {session_id}")
    await AuthStore().create_interview(session_id, user.org_id, candidate_name=name)

    try:
        await livekit_service.create_room(room_name)
        await livekit_service.dispatch_agent(room_name)
        token = livekit_service.generate_participant_token(
            room_name=room_name,
            participant_identity=f"candidate-{session_id}",
            participant_name=name,
        )
        await active_calls.save({
            "call_id": call_id,
            "session_id": session_id,
            "room_name": room_name,
            "candidate_name": name,
            "org_id": user.org_id,
            "user_id": user.user_id,
            "language": request.language,
            "livekit_url": settings.livekit_url,
            "created_at": datetime.now(UTC).isoformat(),
            "status": "created",
        })
        # The brain starts in the chosen language (the voice agent reads it from the call)
        redis = get_redis_client()
        try:
            await AvatarStreamManager(redis).publish_transcription(
                session_id=session_id,
                content="",
                message_type="system_init",
                extra_fields={"language": request.language},
            )
        finally:
            await redis.aclose()
        await record(
            "call.start", actor_type="user", actor_id=user.user_id,
            org_id=user.org_id, target_type="interview", target_id=session_id,
        )
        logger.info(f"Call {call_id} created successfully")
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
        raise HTTPException(status_code=500, detail="Could not start the session. Please try again.") from e


@router.get("/{call_id}", response_model=CallStatusResponse)
async def get_call_status(call_id: str, user: User = Depends(require_user)) -> CallStatusResponse:
    """Get the status of an active call."""
    call = await active_calls.get(call_id)
    if call is None:
        raise HTTPException(status_code=404, detail="Call not found")
    await ensure_session_user_access(call["session_id"], user)

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


@router.delete("/{call_id}", response_model=EndCallResponse)
async def end_call(call_id: str, user: User = Depends(require_user)) -> EndCallResponse:
    """End an active call: tell the worker to wrap up, then close the room.

    Duplicate requests for a recently ended call return success.
    """
    call = await active_calls.get(call_id)
    if call is None:
        # Checked after the lookup: the claim removes the call and sets this
        # marker atomically, so a call ended meanwhile is never reported missing
        if await active_calls.recently_ended(call_id):
            return EndCallResponse(call_id=call_id, status="ended", message="Call already ended")
        raise HTTPException(status_code=404, detail="Call not found")
    await ensure_session_user_access(call["session_id"], user)

    # Atomically take it out of the live set, so concurrent requests (even on
    # other API instances) don't both clean up
    call = await active_calls.claim_for_ending(call_id)
    if call is None:
        return EndCallResponse(call_id=call_id, status="ended", message="Call already ended")

    try:
        await finish_call(call, "user_ended", publish_end_signal=True)
        await record(
            "call.end", actor_type="user", actor_id=user.user_id,
            org_id=call.get("org_id"), target_type="interview", target_id=call["session_id"],
        )
        return EndCallResponse(call_id=call_id, status="ended", message="Call ended successfully")
    except Exception as e:
        logger.error(f"Error ending call: {e}", exc_info=True)
        # Cleanup failed: put the call back so ending can be retried
        await active_calls.forget_ended(call_id)
        await active_calls.save(call)
        raise HTTPException(status_code=500, detail="Could not end the call cleanly. Please try again.") from e
