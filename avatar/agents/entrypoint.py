"""LiveKit Agent Server entrypoint for study sessions.

This module sets up the LiveKit agent that:
1. Joins the study room when the API dispatches it
2. Runs STT on user audio (via Deepgram)
3. Forwards each completed user turn to Brain Worker via Redis
   (end of turn decided by LiveKit's turn detector)
4. Receives responses and plays them through TTS + Avatar
"""

import asyncio
import json
import logging
import os
import time

# Load environment and set API keys BEFORE importing plugins
from dotenv import load_dotenv

load_dotenv()

from core.config import settings

# Set API keys in environment - required for LiveKit plugins
os.environ["DEEPGRAM_API_KEY"] = settings.deepgram_api_key
os.environ["SARVAM_API_KEY"] = settings.sarvam_api_key
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
from livekit.plugins import bey, deepgram, noise_cancellation, sarvam, silero

from agents import language as lang
from agents.interview_monitor import End, InterviewMonitor, Notify, Say
from core.redis import get_redis_client
from services import active_calls
from services.call_finisher import finish_session
from services.streams import AvatarStreamManager

logger = logging.getLogger(__name__)

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
        # Raise these in a noisy room (INTERRUPT_MIN_DURATION / INTERRUPT_MIN_WORDS)
        "min_duration": settings.interrupt_min_duration,
        "min_words": settings.interrupt_min_words,
        "resume_false_interruption": True,
        "false_interruption_timeout": 1.0,
    },
}


class BuddyVoice:
    """Speaks each line in the language of its words (agents/language.py).

    Sarvam TTS sends its language with every new synthesis stream, so switching
    before a line takes effect for that line, pooled connection or not.
    """

    def __init__(self, tts, language: str):
        self.tts = tts
        self.language = language  # language of the last line spoken
        self.switchable = isinstance(tts, sarvam.TTS)

    def prepare(self, text: str) -> None:
        target = lang.language_of(text, self.language)
        if self.switchable and target != self.language:
            self.tts.update_options(target_language_code=target)
            logger.info(f"[VOICE] Speaking {target} (was {self.language})")
        self.language = target


def build_speech(language: str):
    """Speech-to-text and text-to-speech for a session (VOICE_PROVIDER)."""
    if settings.voice_provider == "deepgram":
        # English-only fallback (e.g. if Sarvam is down during a demo)
        return (
            deepgram.STT(model="nova-2", language="en"),
            deepgram.TTS(model=settings.deepgram_tts_model),
        )
    return (
        # language="auto": detects Malayalam/Telugu/English per utterance, so the
        # learner can switch mid-conversation
        sarvam.STTRealtime(language=settings.stt_language),
        sarvam.TTS(
            model=settings.tts_model,
            target_language_code=language,
            speaker=settings.tts_speaker,
        ),
    )


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
        # Language of the learner's latest speech (from speech recognition)
        self.language: str | None = None

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
                    # The brain answers in the language the learner is speaking
                    **({"language": self.language} if self.language else {}),
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
    before_speaking=None,
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
                if before_speaking is not None:
                    before_speaking(message.content)
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

    # Starting language: chosen on the start screen (stored with the call)
    call = await active_calls.get_by_session(session_id)
    start_language = lang.normalize((call or {}).get("language")) or settings.buddy_language

    # Clock rules: silence, dropped connection (agents/interview_monitor.py)
    monitor = InterviewMonitor(now=time.time())

    # Completed turns (as decided by LiveKit's turn detector) go to the Brain Worker
    relay = TurnRelay(session_id=session_id, stream_manager=stream_manager, monitor=monitor)
    hang_up = asyncio.Event()

    # Event to signal when to stop the response listener
    stop_event = asyncio.Event()
    listener_task: asyncio.Task | None = None

    try:
        # Create agent session with STT, TTS, VAD (NO LLM - Brain Worker handles this)
        stt, tts = build_speech(start_language)
        voice = BuddyVoice(tts, start_language)
        relay.language = start_language
        session = AgentSession(
            stt=stt,
            tts=tts,
            vad=ctx.proc.userdata["vad"],
            turn_handling=TURN_HANDLING,
        )

        def on_user_input_transcribed(ev: agents.voice.UserInputTranscribedEvent) -> None:
            if ev.is_final and ev.transcript and ev.transcript.strip():
                spoken = lang.normalize(ev.language)
                if spoken:
                    relay.language = spoken
                logger.info(f"[STT Final] User ({session_id}, {ev.language}): {ev.transcript}")

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
                        # In the language we're speaking now
                        text = lang.nudge(action.key, voice.language) or action.text
                        await _record_line(redis, session_id, text)
                        voice.prepare(text)
                        session.say(text, allow_interruptions=True)
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

        # BeyondPresence video avatar (identity must contain 'bey'/'avatar' for the
        # frontend). Optional: if it fails, the buddy still talks, voice-only.
        if settings.enable_avatar and settings.bey_api_key:
            try:
                avatar = bey.AvatarSession(
                    avatar_id=settings.bey_avatar_id,
                    avatar_participant_identity="bey-avatar",
                    avatar_participant_name=settings.agent_name,
                )
                await avatar.start(session, room=ctx.room)
                logger.info(f"Avatar started for session {session_id}")
            except Exception as e:
                logger.warning(f"Avatar unavailable for {session_id}, continuing voice-only: {e}")

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
                before_speaking=voice.prepare,
            )
        )

        # The buddy says hello first (spoken by the agent; the brain answers from then on)
        greeting = lang.greeting(start_language)
        voice.prepare(greeting)
        logger.info(f"Speaking initial greeting for session {session_id}")
        await session.say(greeting, allow_interruptions=True)
        logger.info(f"Initial greeting complete for session {session_id}")

        # Once a second: apply the clock rules, and hang up when the session is over
        while ctx.room.connection_state == rtc.ConnectionState.CONN_CONNECTED:
            now = time.time()
            try:
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


def prewarm(proc: JobProcess) -> None:
    """Load the VAD model once per process instead of on every call."""
    proc.userdata["vad"] = silero.VAD.load()


if __name__ == "__main__":
    # Run the agent using LiveKit CLI
    # Production runs `start`: SIGTERM drains (no new interviews, running ones
    # finish) for up to agent_drain_timeout_seconds before exiting
    cli.run_app(
        agents.WorkerOptions(
            entrypoint_fnc=entrypoint,
            # Explicit dispatch only (api/call_routes.py): other agents on the same
            # LiveKit project can't take our calls, and ours won't take theirs
            agent_name=settings.agent_dispatch_name,
            prewarm_fnc=prewarm,
            drain_timeout=settings.agent_drain_timeout_seconds,
            # dev keeps LiveKit's random port so local runs don't collide
            port=ServerEnvOption(dev_default=0, prod_default=settings.agent_health_port),
        )
    )
