"""Clock-based rules for the live session, applied by the voice agent.

Silence after a question and dropped connections. Pure logic with an injected
clock, so it can be tested without LiveKit; agents/entrypoint.py feeds it
events and carries out the actions it returns. Conversation-level rules (time
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

    reason: str  # no_response | disconnected


Action = Say | Notify | End


class InterviewMonitor:
    def __init__(self, now: float, policy: MonitorPolicy = POLICY):
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

        self.last_speech_at = now

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

    def prompt_failed(self) -> None:
        """A nudge couldn't be spoken: the next speech is not that nudge."""
        self._next_stop_is_prompt = False

    def take_latency_ms(self) -> int | None:
        """Thinking time before the turn just completed (sent with the turn)."""
        latency, self._pending_latency_ms = self._pending_latency_ms, None
        return latency

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

        if self.agent_speaking:
            return []

        return self._silence_tick(now)

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
