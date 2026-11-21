"""Ending a call: one path for the End button and for the voice agent.

The voice agent ends sessions itself (silence, connection lost, or after the
goodbye of a session the worker concluded), so the cleanup
lives here rather than in the HTTP route.
"""

import logging

from core.interviews import now, update_interview
from core.redis import get_redis_client
from services import active_calls
from services.livekit_service import livekit_service
from services.streams import AvatarStreamManager

logger = logging.getLogger(__name__)


async def finish_call(call: dict, end_reason: str, *, publish_end_signal: bool) -> None:
    """Clean up a call already claimed with active_calls.claim_for_ending.

    publish_end_signal: tell the worker to conclude (the End button). The voice
    agent's ends are already known to the worker.
    """
    session_id = call["session_id"]

    if publish_end_signal:
        # Triggers the conclude step, which writes the report
        try:
            redis = get_redis_client()
            try:
                await AvatarStreamManager(redis).publish_transcription(
                    session_id=session_id,
                    content="",
                    message_type="end_call",
                    extra_fields={"end_reason": end_reason},
                )
            finally:
                await redis.aclose()
            logger.info(f"Published end_call signal for session {session_id}")
        except Exception as e:
            # Don't fail the cleanup; the worker's inactivity sweep ends it later
            logger.warning(f"Failed to publish end_call signal: {e}")

    await update_interview(
        session_id,
        status="ended",
        ended_at=now(),
        end_reason=end_reason,
    )

    # Disconnects everyone; a rejoin is refused from now on (no active call)
    await livekit_service.delete_room(call["room_name"])


async def finish_session(session_id: str, end_reason: str) -> bool:
    """End a session's call from the voice agent. False if it was already ended."""
    call = await active_calls.get_by_session(session_id)
    if call is None:
        return False
    call = await active_calls.claim_for_ending(call["call_id"])
    if call is None:
        return False
    try:
        await finish_call(call, end_reason, publish_end_signal=False)
    except Exception:
        await active_calls.forget_ended(call["call_id"])
        await active_calls.save(call)
        raise
    logger.info(f"Call for session {session_id} ended by the agent ({end_reason})")
    return True
