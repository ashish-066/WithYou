"""Clock-based rules for the live interview, applied by the voice agent.

Silence after a question, coding-round prompts, leaving the camera view and
dropped connections. Pure logic with an injected clock, so it can be tested
without LiveKit; agents/entrypoint.py feeds it events and carries out the
actions it returns.

Principle: nothing the candidate does buys unobserved time. The clock never
stops; an absence costs the current question (the worker replaces it) and
repeated or long absences end the interview. Conversation-level rules (time
budget, wrap-up, goodbyes) are in the worker: worker/brain/interview_flow.py.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MonitorPolicy:
    # Silence after a question (technical round)
    repeat_offer_s: float = 10.0
    move_on_s: float = 30.0
    max_unanswered_in_a_row: int = 3
    # Unanswered silence over the whole interview (4 questions x 30 s)
    max_total_silence_s: float = 120.0
    # Coding round
    talk_through_s: float = 120.0  # typing without a word
    typing_recent_s: float = 30.0  # counts as "typing" if code changed this recently
    stuck_s: float = 60.0  # no typing and no speech
    min_prompt_gap_s: float = 180.0  # at most one interjection per 3 min
    # Camera view
    face_warn_s: float = 10.0
    face_end_s: float = 60.0
    max_absences: int = 3
    # Camera checks stopped arriving while connected (camera off or blocked)
    presence_stale_s: float = 20.0
    # Connection
    rejoin_window_s: float = 120.0
    max_rejoins: int = 1
    # Goodbye, then hang up
    hangup_delay_s: float = 5.0
    # If the worker never sends the goodbye after an end, hang up anyway
    end_fallback_s: float = 60.0


POLICY = MonitorPolicy()

LINES = {
    "repeat_offer": "Take your time. Would you like me to repeat the question?",
    "talk_through": "Can you talk me through what you're writing?",
    "stuck": "Where are you stuck? I can give you a hint if you'd like.",
    "come_back": "I can't see you on camera. Please come back into view.",
    "too_dark": "Your camera image is too dark for me to see you. Please turn on a light.",
    "put_phone_away": "I can see a phone. Please put it away, out of reach, for the rest of the interview.",
    "someone_with_you": (
        "It looks like someone else is with you. The interview needs to be done alone, "
        "so please make sure you're by yourself."
    ),
}


@dataclass
class Say:
    """A short line the agent speaks itself (not a new interview question)."""

    key: str

    @property
    def text(self) -> str:
        return LINES[self.key]


@dataclass
class Notify:
    """An event for the worker: question_unanswered | candidate_returned."""

    message_type: str


@dataclass
class End:
    """End the interview; the worker writes the goodbye and the report."""

    reason: str  # no_response | left_view | disconnected


Action = Say | Notify | End


class InterviewMonitor:
    def __init__(self, coding: bool, now: float, policy: MonitorPolicy = POLICY):
        self.coding = coding
        self.p = policy
        self.ended: str | None = None
        self.ended_at: float | None = None

        # Turn-taking
        self.agent_speaking = False
        self.question_end: float | None = None  # waiting for an answer since
        self.repeat_offered = False
        self._next_stop_is_prompt = False
        self._pending_latency_ms: int | None = None

        # Silence bookkeeping
        self.unanswered_in_a_row = 0
        self.silence_total_s = 0.0

        # Coding round
        self.last_code_at: float | None = None
        self.last_speech_at = now
        self.last_prompt_at: float | None = None
        self.stuck_prompted_at: float | None = None

        # Camera
        self.face_absent_since: float | None = None
        self.absence_counted = False
        self.absences = 0
        self.presence_seen_at: float | None = None
        self._queued_return = False
        self.dark = False

        # Connection
        self.left_at: float | None = None
        self.rejoins = 0

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def agent_started_speaking(self, now: float) -> None:
        self.agent_speaking = True

    def agent_stopped_speaking(self, now: float) -> None:
        self.agent_speaking = False
        self.last_speech_at = now
        if self._next_stop_is_prompt:
            # Our own nudge: the question's clock keeps running
            self._next_stop_is_prompt = False
            return
        # A new question (or reply) has been asked: wait for the answer
        self.question_end = now
        self.repeat_offered = False

    def user_started_speaking(self, now: float) -> None:
        self.last_speech_at = now
        if self.question_end is not None:
            if self._pending_latency_ms is None:
                self._pending_latency_ms = int((now - self.question_end) * 1000)
            self.question_end = None
        self.unanswered_in_a_row = 0
        self.stuck_prompted_at = None

    def prompt_failed(self) -> None:
        """A nudge couldn't be spoken: the next speech is not that nudge."""
        self._next_stop_is_prompt = False

    def take_latency_ms(self) -> int | None:
        """Thinking time before the turn just completed (sent with the turn)."""
        latency, self._pending_latency_ms = self._pending_latency_ms, None
        return latency

    def code_activity(self, now: float) -> None:
        self.last_code_at = now
        self.stuck_prompted_at = None

    def presence(self, now: float, face_visible: bool, dark: bool = False) -> None:
        """A camera check (agents/vision_monitor.py, on the candidate's video)."""
        self.presence_seen_at = now
        self.dark = dark
        if face_visible:
            self._face_back(now)
        elif self.face_absent_since is None:
            self.face_absent_since = now

    def participant_left(self, now: float) -> list[Action]:
        if self.ended:
            return []
        self.left_at = now
        if self.rejoins >= self.p.max_rejoins:
            return self._end("disconnected", now)
        return []

    def participant_joined(self, now: float) -> list[Action]:
        if self.left_at is None or self.ended:
            return []
        self.left_at = None
        self.rejoins += 1
        return self._returned(now)

    # ------------------------------------------------------------------
    # Clock
    # ------------------------------------------------------------------

    def tick(self, now: float) -> list[Action]:
        if self.ended:
            return []

        # Disconnected: wait for a rejoin, nothing else applies
        if self.left_at is not None:
            if now - self.left_at >= self.p.rejoin_window_s:
                return self._end("disconnected", now)
            return []

        # Camera checks stopped arriving: treat as out of view
        if (
            self.presence_seen_at is not None
            and self.face_absent_since is None
            and now - self.presence_seen_at >= self.p.presence_stale_s
        ):
            self.face_absent_since = self.presence_seen_at

        # Out of view
        if self.face_absent_since is not None:
            away = now - self.face_absent_since
            if away >= self.p.face_end_s:
                return self._end("left_view", now)
            if away >= self.p.face_warn_s and not self.absence_counted:
                self.absence_counted = True
                self.absences += 1
                if self.absences >= self.p.max_absences:
                    return self._end("left_view", now)
                return [self._say("too_dark" if self.dark else "come_back")]
            return []

        if self.agent_speaking:
            return []

        return self._coding_tick(now) if self.coding else self._silence_tick(now)

    def should_hang_up_anyway(self, now: float) -> bool:
        """The worker never confirmed the end: hang up without its goodbye."""
        return self.ended_at is not None and now - self.ended_at >= self.p.end_fallback_s

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _silence_tick(self, now: float) -> list[Action]:
        if self.question_end is None:
            return []
        waited = now - self.question_end
        if waited >= self.p.move_on_s:
            return self._unanswered(waited, now)
        if waited >= self.p.repeat_offer_s and not self.repeat_offered:
            self.repeat_offered = True
            return [self._say("repeat_offer")]
        return []

    def _coding_tick(self, now: float) -> list[Action]:
        typing = self.last_code_at is not None and now - self.last_code_at < self.p.typing_recent_s
        since_speech = now - self.last_speech_at
        gap_ok = self.last_prompt_at is None or now - self.last_prompt_at >= self.p.min_prompt_gap_s

        # Typing without explaining: ask them to think aloud
        if typing and since_speech >= self.p.talk_through_s and gap_ok:
            self.last_prompt_at = now
            return [self._say("talk_through")]

        if typing:
            return []

        # Neither typing nor talking
        idle_since = max(self.last_speech_at, self.last_code_at or 0.0)
        idle = now - idle_since
        if self.stuck_prompted_at is None:
            if idle >= self.p.stuck_s:
                self.stuck_prompted_at = now
                self.last_prompt_at = now
                return [self._say("stuck")]
            return []
        # Still nothing a minute after "where are you stuck?"
        if now - self.stuck_prompted_at >= self.p.stuck_s:
            self.stuck_prompted_at = None
            self.last_speech_at = now  # the worker's next question restarts the clock
            return self._unanswered(self.p.stuck_s, now)
        return []

    def _unanswered(self, waited: float, now: float) -> list[Action]:
        self.question_end = None
        self.unanswered_in_a_row += 1
        self.silence_total_s += waited
        if (
            self.unanswered_in_a_row >= self.p.max_unanswered_in_a_row
            or self.silence_total_s >= self.p.max_total_silence_s
        ):
            return self._end("no_response", now)
        return [Notify("question_unanswered")]

    def _face_back(self, now: float) -> None:
        if self.face_absent_since is None:
            return
        counted = self.absence_counted
        self.face_absent_since = None
        self.absence_counted = False
        if counted:
            # Only an absence long enough to warn about costs the question
            self._queued_return = True

    def drain_returns(self, now: float) -> list[Action]:
        """Actions owed for a return to view (called by the agent after presence())."""
        if self._queued_return and not self.ended:
            self._queued_return = False
            return self._returned(now)
        return []

    def _returned(self, now: float) -> list[Action]:
        self.question_end = None
        self.repeat_offered = False
        return [Notify("candidate_returned")]

    def _say(self, key: str) -> Say:
        self._next_stop_is_prompt = True
        return Say(key)

    def _end(self, reason: str, now: float) -> list[Action]:
        self.ended = reason
        self.ended_at = now
        return [End(reason)]
