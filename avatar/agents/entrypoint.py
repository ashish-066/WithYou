"""LiveKit Agent Server entrypoint for interview sessions.

This module sets up the LiveKit agent that:
1. Joins interview rooms when candidates connect
2. Runs STT on user audio (via Deepgram)
3. Forwards each completed user turn to Brain Worker via Redis
   (end of turn decided by LiveKit's turn detector)
4. Receives responses and plays them through TTS + Avatar
"""

import asyncio
import hashlib
import json
import logging
import os
import time
import uuid
from datetime import UTC, datetime

# Load environment and set API keys BEFORE importing plugins
from dotenv import load_dotenv

load_dotenv()

from core.config import settings

# Set API keys in environment - required for LiveKit plugins
os.environ["DEEPGRAM_API_KEY"] = settings.deepgram_api_key
os.environ["CARTESIA_API_KEY"] = settings.cartesia_api_key
os.environ["BEY_API_KEY"] = settings.bey_api_key
os.environ["LIVEKIT_URL"] = settings.livekit_url
os.environ["LIVEKIT_API_KEY"] = settings.livekit_api_key
os.environ["LIVEKIT_API_SECRET"] = settings.livekit_api_secret

# Now import LiveKit agents and plugins
from livekit import agents, rtc
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    JobProcess,
    RoomInputOptions,
    StopResponse,
    cli,
)
from livekit.agents.worker import ServerEnvOption
from livekit.plugins import bey, cartesia, deepgram, noise_cancellation, silero

from agents.interview_monitor import End, InterviewMonitor, Notify, Say
from agents.vision import get_models
from agents.vision_monitor import CANDIDATE_NOTICES, VisionMonitor
from api.proctoring_routes import _queue_flags as queue_flags
from api.proctoring_routes import _timeline_note as timeline_note
from core.recordings import evidence_key, put_evidence
from core.redis import get_redis_client
from services import active_calls
from services.call_finisher import finish_session
from services.presence import code_activity_key, to_epoch
from services.streams import AvatarStreamManager

logger = logging.getLogger(__name__)

# Data channel topic for notices to the candidate's page (frontend: CameraWarning)
PROCTORING_TOPIC = "proctoring"

# How LiveKit decides the candidate finished a turn and when Presence may be cut off.
# The default turn detector (LiveKit Cloud inference) judges from the words whether
# the candidate is done, waiting min_delay after a complete thought and up to
# max_delay after an unfinished one — replaces a fixed 1.5s silence timer.
TURN_HANDLING = {
    "endpointing": {"min_delay": 0.5, "max_delay": 3.0},
    "interruption": {
        # Presence's audio is paused as soon as candidate speech is detected. Requiring
        # transcribed words stops coughs, keyboard noise and echo from cutting
        # Presence off mid-sentence (the "voice breaking").
        "min_duration": 0.8,
        "min_words": 2,
        "resume_false_interruption": True,
        "false_interruption_timeout": 1.0,
    },
}


class TurnRelay:
    """Publishes completed candidate turns to the Brain Worker via Redis."""

    def __init__(
        self,
        session_id: str,
        stream_manager: AvatarStreamManager,
        monitor: InterviewMonitor | None = None,
    ):
        self.session_id = session_id
        self.stream_manager = stream_manager
        self.monitor = monitor
        self._lock = asyncio.Lock()
        # Highest turn number successfully sent; the Brain echoes it back as
        # reply_to_seq so replies to turns the candidate already talked past can be
        # dropped. _next_seq allocates numbers (overlapping sends stay unique).
        self.turn_seq = 0
        self._next_seq = 0

    async def send(self, text: str) -> None:
        full_text = text.strip()
        if not full_text:
            return

        async with self._lock:
            self._next_seq += 1
            seq = self._next_seq

        logger.info(f"[STT] Forwarding user turn to Brain ({self.session_id}): {full_text}")
        latency = self.monitor.take_latency_ms() if self.monitor else None
        try:
            message_id = await self.stream_manager.publish_transcription(
                session_id=self.session_id,
                content=full_text,
                message_type="candidate_response",
                extra_fields={
                    "turn_seq": seq,
                    # Time from the end of the question to the first word
                    **({"response_latency_ms": latency} if latency is not None else {}),
                },
            )
            # Only count the turn once it's actually sent, otherwise a failed
            # publish would make the listener drop the reply to the previous turn
            self.turn_seq = max(self.turn_seq, seq)
            logger.info(f"[STT] Published to Redis {message_id}: {full_text[:80]}")
        except Exception as e:
            logger.error(f"[STT] Failed to publish transcription to Redis: {e}", exc_info=True)


class BrainRelayAgent(Agent):
    """Agent with no LLM: hands each completed user turn to the Brain Worker."""

    def __init__(self, relay: TurnRelay):
        super().__init__(instructions="")
        self._relay = relay

    async def on_user_turn_completed(self, turn_ctx, new_message) -> None:
        await self._relay.send(new_message.text_content or "")
        # Replies come from the Brain Worker over Redis, not from this session
        raise StopResponse()


async def listen_for_brain_responses(
    session_id: str,
    stream_manager: AvatarStreamManager,
    session: AgentSession,
    stop_event: asyncio.Event,
    relay: TurnRelay,
    start_id: str | None = None,
    on_interview_ended=None,
) -> None:
    """Background task that listens for Brain Worker responses.

    Consumes messages from interview:responses stream and speaks them.

    Args:
        session_id: The interview session ID to filter for
        stream_manager: Redis stream manager for consuming responses
        session: The LiveKit agent session for TTS playback
        stop_event: Event to signal when to stop listening
        relay: Used to drop replies to turns the candidate already followed up on
        start_id: Stream ID to read after (see AvatarStreamManager.response_start_id)
    """
    logger.info(f"Starting Brain response listener for session {session_id}")

    try:
        async for message in stream_manager.consume_responses(
            session_id=session_id, start_id=start_id
        ):
            if stop_event.is_set():
                logger.info("Stop event set, ending response listener")
                break

            # The interview is over: the goodbye (published just before) has been
            # spoken; hang up shortly after
            if message.message_type == "interview_ended":
                await stream_manager.mark_spoken(session_id, message.message_id)
                if on_interview_ended is not None:
                    await on_interview_ended(message.raw_data.get("end_reason") or "completed")
                continue

            # Candidate spoke again while the Brain was thinking: a reply to the
            # newer turn (which has the full context) is coming, so skip this one.
            reply_to = message.raw_data.get("reply_to_seq")
            if reply_to and reply_to.isdigit() and int(reply_to) < relay.turn_seq:
                logger.info(
                    f"[BRAIN->TTS] Dropping stale reply to turn {reply_to} "
                    f"(latest {relay.turn_seq}) for session {session_id}"
                )
                await stream_manager.mark_spoken(session_id, message.message_id)
                continue

            logger.info(
                f"[BRAIN->TTS] Speaking response for session {session_id}: "
                f"{message.content[:80]}..."
            )

            try:
                # Speak the response through TTS -> Avatar
                await session.say(
                    message.content,
                    allow_interruptions=True,
                )
                logger.info(f"[BRAIN->TTS] Finished speaking response {message.message_id}")
            except Exception as e:
                logger.error(f"Error speaking response: {e}", exc_info=True)
            finally:
                await stream_manager.mark_spoken(session_id, message.message_id)

    except asyncio.CancelledError:
        logger.info(f"Response listener cancelled for session {session_id}")
        raise
    except Exception as e:
        logger.error(f"Error in response listener: {e}", exc_info=True)


async def entrypoint(ctx: JobContext) -> None:
    """Main entrypoint for each interview session.

    This function is called by the LiveKit agent server when a new
    room is created that matches our dispatch rules.

    Args:
        ctx: Job context with room connection and metadata
    """
    # Wait for the room to be ready
    await ctx.connect()

    # Extract session ID from room name (format: interview-{session_id})
    room_name = ctx.room.name
    if room_name.startswith("interview-"):
        session_id = room_name.replace("interview-", "", 1)
    else:
        session_id = room_name

    logger.info(
        f"Starting interview agent for session {session_id} in room {room_name}"
    )

    # Set up Redis stream manager for this session
    redis = get_redis_client()
    stream_manager = AvatarStreamManager(redis)

    # Read replies published since the room was created (e.g. the DSA intro,
    # which can be ready before the agent joins), minus any already spoken.
    room_info = ctx.job.room
    room_created_ms = room_info.creation_time_ms or room_info.creation_time * 1000
    response_start_id = await stream_manager.response_start_id(
        session_id, since_ms=room_created_ms or None
    )

    # Clock rules: silence, camera view, dropped connection (agents/interview_monitor.py)
    call = await active_calls.get_by_session(session_id)
    coding = (call or {}).get("interview_mode") == "round2_dsa"
    monitor = InterviewMonitor(coding=coding, now=time.time())

    # Completed turns (as decided by LiveKit's turn detector) go to the Brain Worker
    relay = TurnRelay(session_id=session_id, stream_manager=stream_manager, monitor=monitor)
    hang_up = asyncio.Event()

    # Event to signal when to stop the response listener
    stop_event = asyncio.Event()
    listener_task: asyncio.Task | None = None
    camera_task: asyncio.Task | None = None

    try:
        # Create agent session with STT, TTS, VAD (NO LLM - Brain Worker handles this)
        session = AgentSession(
            stt=deepgram.STT(
                model="nova-2",
                language="en",
            ),
            tts=cartesia.TTS(
                model="sonic-2",
                voice="3fffe34e-bcfb-4b71-ba11-ff3aba4d6c6f",  # Chetan - Casual Storyteller
            ),
            vad=ctx.proc.userdata["vad"],
            turn_handling=TURN_HANDLING,
        )

        def on_user_input_transcribed(ev: agents.voice.UserInputTranscribedEvent) -> None:
            if ev.is_final and ev.transcript and ev.transcript.strip():
                logger.debug(f"[STT Final] User ({session_id}): {ev.transcript}")

        def on_false_interruption(ev: agents.voice.AgentFalseInterruptionEvent) -> None:
            # Presence was paused by candidate-side sound that turned out not to be speech
            logger.info(f"[Interruption] False interruption for {session_id} (resumed={ev.resumed})")

        def on_agent_state(ev: agents.voice.AgentStateChangedEvent) -> None:
            if ev.new_state == "speaking":
                monitor.agent_started_speaking(time.time())
            elif ev.old_state == "speaking":
                monitor.agent_stopped_speaking(time.time())

        def on_user_state(ev: agents.voice.UserStateChangedEvent) -> None:
            if ev.new_state == "speaking":
                monitor.user_started_speaking(time.time())

        session.on("user_input_transcribed", on_user_input_transcribed)
        session.on("agent_false_interruption", on_false_interruption)
        session.on("agent_state_changed", on_agent_state)
        session.on("user_state_changed", on_user_state)

        candidate_identity = f"candidate-{session_id}"

        async def run_actions(actions) -> None:
            for action in actions:
                if isinstance(action, Say):
                    # Our own short nudge; it doesn't restart the question's clock
                    logger.info(f"[MONITOR] {session_id}: saying '{action.key}'")
                    try:
                        await _record_line(redis, session_id, action.text)
                        session.say(action.text, allow_interruptions=True)
                    except Exception as e:
                        monitor.prompt_failed()
                        logger.warning(f"[MONITOR] Could not speak nudge: {e}")
                elif isinstance(action, Notify):
                    logger.info(f"[MONITOR] {session_id}: {action.message_type}")
                    await stream_manager.publish_transcription(
                        session_id=session_id, content="", message_type=action.message_type
                    )
                elif isinstance(action, End):
                    # The worker concludes (report, goodbye), then signals the hang-up
                    logger.info(f"[MONITOR] {session_id}: ending interview ({action.reason})")
                    await stream_manager.publish_transcription(
                        session_id=session_id,
                        content="",
                        message_type="end_call",
                        extra_fields={"end_reason": action.reason},
                    )

        def on_participant_disconnected(participant: rtc.RemoteParticipant) -> None:
            if participant.identity == candidate_identity:
                logger.info(f"[MONITOR] {session_id}: candidate left the room")
                asyncio.create_task(run_actions(monitor.participant_left(time.time())))

        def on_participant_connected(participant: rtc.RemoteParticipant) -> None:
            if participant.identity == candidate_identity:
                logger.info(f"[MONITOR] {session_id}: candidate rejoined")
                asyncio.create_task(run_actions(monitor.participant_joined(time.time())))

        ctx.room.on("participant_disconnected", on_participant_disconnected)
        ctx.room.on("participant_connected", on_participant_connected)

        # Camera checks on the candidate's video, on this server (agents/vision.py):
        # presence for the clock rules, and flags with photo evidence
        vision = VisionMonitor()
        camera_task: asyncio.Task | None = None
        call_started = to_epoch((call or {}).get("created_at")) or time.time()

        async def report_finding(finding, rgb) -> None:
            flag_id = str(uuid.uuid4())
            evidence: dict = {
                "detections": [d.as_dict() for d in finding.detections],
                "model": "efficientdet_lite0 + blaze_face_short_range",
                # Where to look in the recording (it starts with the call)
                "recording_seconds": round(time.time() - call_started, 1),
            }
            if finding.with_photo and rgb is not None:
                jpeg = _encode_jpeg(rgb)
                key = evidence_key(session_id, flag_id)
                if await asyncio.to_thread(put_evidence, key, jpeg):
                    evidence.update(
                        photo_key=key,
                        sha256=hashlib.sha256(jpeg).hexdigest(),
                        frame_size=[int(rgb.shape[1]), int(rgb.shape[0])],
                    )
            started_at, turn = await redis.hmget(f"context:{session_id}", "started_at", "turn_count")
            flag = {
                "id": flag_id,
                "flag_type": finding.flag_type,
                "severity": finding.severity,
                "confidence": round(finding.confidence, 3),
                "description": f"{finding.description} ({finding.confidence:.0%} confidence)",
                "evidence": evidence,
                "timestamp": datetime.now(UTC).isoformat(),
                "turn_number": int(turn or 0),
                "source": "server_camera_check",
            }
            await queue_flags(session_id, [flag], [timeline_note(flag, started_at)])
            logger.info(f"[VISION] {session_id}: {finding.kind} flagged ({finding.confidence:.2f})")

        async def show_notice(kind: str) -> None:
            """Pop-up for the candidate (their page listens on the proctoring topic)."""
            title, message = CANDIDATE_NOTICES.get(kind, ("", ""))
            if not title:
                return
            try:
                await ctx.room.local_participant.publish_data(
                    json.dumps({"type": "camera_warning", "kind": kind, "title": title, "message": message}),
                    reliable=True,
                    destination_identities=[candidate_identity],
                    topic=PROCTORING_TOPIC,
                )
            except Exception as e:
                logger.warning(f"[VISION] {session_id}: could not show the candidate a notice: {e}")

        async def watch_camera(track: rtc.Track) -> None:
            stream = rtc.VideoStream(track, capacity=1, format=rtc.VideoBufferType.RGB24)
            models = ctx.proc.userdata.get("vision") or get_models()
            recent: dict[int, object] = {}
            index = 0
            spoken: set[str] = set()
            try:
                async for event in stream:
                    now = time.time()
                    if not vision.wants_frame(now):
                        continue
                    frame = event.frame
                    rgb = _frame_to_rgb(frame)
                    objects = vision.wants_objects(now)
                    result = await asyncio.to_thread(models.analyze, rgb, objects)
                    index += 1
                    if objects:
                        recent[index] = rgb
                        for old in [k for k in recent if k < index - 4]:
                            del recent[old]
                    visible, findings = vision.observe(now, result, objects, index)
                    monitor.presence(now, visible, dark=vision.dark)
                    await run_actions(monitor.drain_returns(now))
                    for finding in findings:
                        # Pop-up on the candidate's screen every time; spoken the first time
                        await show_notice(finding.kind)
                        line = {"multiple_people": "someone_with_you", "phone": "put_phone_away"}.get(finding.kind)
                        if line and line not in spoken:
                            spoken.add(line)
                            await run_actions([Say(line)])
                        await report_finding(finding, recent.get(finding.frame_index))
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"[VISION] {session_id}: camera checks stopped: {e}", exc_info=True)
            finally:
                await stream.aclose()

        def start_camera(track: rtc.Track, publication, participant) -> None:
            nonlocal camera_task
            if (
                participant.identity == candidate_identity
                and track.kind == rtc.TrackKind.KIND_VIDEO
                and publication.source == rtc.TrackSource.SOURCE_CAMERA
            ):
                if camera_task is not None:
                    camera_task.cancel()
                logger.info(f"[VISION] {session_id}: watching the candidate's camera")
                camera_task = asyncio.create_task(watch_camera(track))

        ctx.room.on("track_subscribed", start_camera)
        for participant in ctx.room.remote_participants.values():
            for publication in participant.track_publications.values():
                if publication.track is not None:
                    start_camera(publication.track, publication, participant)

        # Start the BeyondPresence avatar with predictable identity for frontend detection
        avatar = bey.AvatarSession(
            avatar_id=settings.bey_avatar_id,
            avatar_participant_identity="bey-avatar",  # Must contain 'bey' or 'avatar' for frontend
            avatar_participant_name=settings.agent_name,  # Display name (e.g., "Presence")
        )

        # Start avatar first
        await avatar.start(session, room=ctx.room)
        logger.info(f"Avatar started for session {session_id}")

        # Start the agent session with room input. BVC (LiveKit Cloud) removes
        # background voices and noise before VAD/STT, so they don't trigger
        # interruptions; a bare True here is not a valid option and did nothing.
        await session.start(
            BrainRelayAgent(relay),
            room=ctx.room,
            room_input_options=RoomInputOptions(
                noise_cancellation=noise_cancellation.BVC(),
            ),
        )
        logger.info(f"Agent session started for session {session_id}")

        # Start listening for Brain Worker responses in background
        listener_task = asyncio.create_task(
            listen_for_brain_responses(
                session_id=session_id,
                stream_manager=stream_manager,
                session=session,
                stop_event=stop_event,
                relay=relay,
                start_id=response_start_id,
                on_interview_ended=lambda reason: _schedule_hang_up(hang_up, monitor),
            )
        )

        # Initial greeting to welcome the candidate
        greeting = (
            f"Hello! I'm {settings.agent_name}, your AI interviewer today. "
            "It's great to meet you! Whenever you're ready, please introduce yourself and we can begin."
        )
        logger.info(f"Speaking initial greeting for session {session_id}")
        await session.say(greeting, allow_interruptions=True)
        logger.info(f"Initial greeting complete for session {session_id}")

        # Once a second: read coding activity, apply the clock rules, and hang
        # up when the interview is over (camera checks run in watch_camera)
        last_code_at: float | None = None
        while ctx.room.connection_state == rtc.ConnectionState.CONN_CONNECTED:
            now = time.time()
            try:
                code_at = to_epoch(await redis.get(code_activity_key(session_id)))
                if code_at is not None and code_at != last_code_at:
                    last_code_at = code_at
                    monitor.code_activity(code_at)
                await run_actions(monitor.tick(now))
            except Exception as e:
                logger.warning(f"[MONITOR] {session_id}: tick failed: {e}")

            if hang_up.is_set() or monitor.should_hang_up_anyway(now):
                reason = monitor.ended or "completed"
                await asyncio.sleep(monitor.p.hangup_delay_s)
                try:
                    await finish_session(session_id, reason)
                except Exception as e:
                    logger.error(f"[MONITOR] {session_id}: could not end the call: {e}")
                break
            await asyncio.sleep(1)

    except Exception as e:
        logger.error(f"Error in interview agent: {e}", exc_info=True)
        raise
    finally:
        # Signal listener to stop
        stop_event.set()

        if camera_task is not None:
            camera_task.cancel()

        # Cancel listener task
        if listener_task is not None:
            listener_task.cancel()
            try:
                await listener_task
            except asyncio.CancelledError:
                pass

        # Cleanup Redis connection
        await redis.aclose()
        logger.info(f"Interview agent stopped for session {session_id}")


async def _schedule_hang_up(hang_up: asyncio.Event, monitor: InterviewMonitor) -> None:
    """The worker has concluded the interview and its goodbye was spoken."""
    monitor.ended = monitor.ended or "completed"
    hang_up.set()


async def _record_line(redis, session_id: str, text: str) -> None:
    """Add the agent's own nudges to the full transcript (format of the worker's
    services/transcript.py)."""
    from datetime import UTC, datetime

    key = f"transcript:{session_id}"
    entry = {"role": "assistant", "content": text, "timestamp": datetime.now(UTC).isoformat(), "turn": None}
    await redis.rpush(key, json.dumps(entry))
    await redis.expire(key, 30 * 24 * 3600)


def _frame_to_rgb(frame: rtc.VideoFrame):
    """RGB24 frame as [H, W, 3] uint8, scaled down to at most 640 px wide."""
    import numpy as np
    from PIL import Image

    rgb = np.frombuffer(frame.data, dtype=np.uint8).reshape(frame.height, frame.width, 3)
    if frame.width > 640:
        h = round(frame.height * 640 / frame.width)
        rgb = np.asarray(Image.fromarray(rgb).resize((640, h), Image.BILINEAR))
    return rgb


def _encode_jpeg(rgb) -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.fromarray(rgb).save(buf, format="JPEG", quality=80)
    return buf.getvalue()


def prewarm(proc: JobProcess) -> None:
    """Load the VAD and camera-check models once per process instead of on every call."""
    proc.userdata["vad"] = silero.VAD.load()
    proc.userdata["vision"] = get_models()


if __name__ == "__main__":
    # Run the agent using LiveKit CLI
    # Production runs `start`: SIGTERM drains (no new interviews, running ones
    # finish) for up to agent_drain_timeout_seconds before exiting
    cli.run_app(
        agents.WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
            drain_timeout=settings.agent_drain_timeout_seconds,
            # dev keeps LiveKit's random port so local runs don't collide
            port=ServerEnvOption(dev_default=0, prod_default=settings.agent_health_port),
        )
    )
