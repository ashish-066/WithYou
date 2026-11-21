"""When to look at the candidate's video, and when a detection becomes a flag.

Pure logic with an injected clock (tested without models or LiveKit);
agents/entrypoint.py feeds it frames' results and acts on what it returns.

- Cheap first: faces every 2 s; objects (people, phones, laptops) every 4 s,
  and every check for 10 s after anything suspicious.
- A flag needs the same finding in 2 of the last 3 object checks.
- One flag per kind per 30 s, at most 20 evidence photos per interview; the
  photo kept is the frame with the most confident detection.
- Presence for agents/interview_monitor.py: a face, or a large person box
  (head turned), counts as in view; a too-dark frame does not.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from agents.vision import Detection, FrameResult


@dataclass(frozen=True)
class VisionPolicy:
    face_every_s: float = 2.0
    objects_every_s: float = 4.0
    burst_s: float = 10.0
    confirm_hits: int = 2
    confirm_window: int = 3
    flag_cooldown_s: float = 30.0
    max_photos: int = 20
    # Mean luminance below this: the camera is too dark (or covered)
    dark_below: float = 25.0
    # A person box at least this big counts as "the candidate is there"
    present_person_area: float = 0.08
    # Ignore tiny person boxes (posters, background) for "another person"
    other_person_min_area: float = 0.02


POLICY = VisionPolicy()

# Pop-up shown to the candidate when a flag is confirmed (title, message)
CANDIDATE_NOTICES = {
    "phone": (
        "Phone detected",
        "A phone is visible on your camera. Put it away, out of reach, for the rest of the interview. "
        "This has been recorded for the hiring team.",
    ),
    "multiple_people": (
        "Another person detected",
        "Someone else appears to be with you. The interview must be done alone. "
        "This has been recorded for the hiring team.",
    ),
    "laptop": (
        "Another device detected",
        "Another laptop or screen is visible on your camera. Put it away for the rest of the interview. "
        "This has been recorded for the hiring team.",
    ),
}

# Flag types used by the worker's integrity score (worker/services/anti_cheat.py)
FLAGS = {
    "multiple_people": ("multiple_faces", "high", "Another person in view"),
    "phone": ("phone_detected", "high", "Phone in view"),
    "laptop": ("second_screen", "medium", "Another laptop in view"),
}


@dataclass
class Finding:
    """A confirmed flag, with the frame that best shows it."""

    kind: str  # multiple_people | phone | laptop
    flag_type: str
    severity: str
    description: str
    confidence: float
    detections: list[Detection]
    frame_index: int  # which analyzed frame is the evidence (see VisionMonitor.observe)
    with_photo: bool


@dataclass
class _Track:
    hits: deque = field(default_factory=lambda: deque(maxlen=POLICY.confirm_window))
    best: tuple[float, int, list[Detection]] | None = None  # confidence, frame, detections
    last_flag_at: float | None = None


class VisionMonitor:
    def __init__(self, policy: VisionPolicy = POLICY):
        self.p = policy
        self._last_face_at: float | None = None
        self._last_objects_at: float | None = None
        self._burst_until = 0.0
        self._tracks = {kind: _Track(deque(maxlen=policy.confirm_window)) for kind in FLAGS}
        self._photos = 0
        self._last_persons: list[Detection] = []
        self._last_objects_check: float | None = None
        self.dark = False

    # ------------------------------------------------------------------
    # Scheduling
    # ------------------------------------------------------------------

    def wants_frame(self, now: float) -> bool:
        return self._last_face_at is None or now - self._last_face_at >= self.p.face_every_s

    def wants_objects(self, now: float) -> bool:
        if self._last_objects_at is None:
            return True
        every = self.p.face_every_s if now < self._burst_until else self.p.objects_every_s
        return now - self._last_objects_at >= every

    # ------------------------------------------------------------------
    # Results
    # ------------------------------------------------------------------

    def observe(self, now: float, result: FrameResult, objects_checked: bool, frame_index: int) -> tuple[bool, list[Finding]]:
        """Returns (candidate visible, confirmed findings)."""
        self._last_face_at = now
        self.dark = result.brightness < self.p.dark_below

        findings: list[Finding] = []
        if objects_checked:
            self._last_objects_at = now
            self._last_objects_check = now
            self._last_persons = result.of("person")
            current = self._signals(result)
            if any(current.values()) or len(result.faces) != 1:
                self._burst_until = now + self.p.burst_s
            for kind, dets in current.items():
                findings += self._update(kind, dets, now, frame_index)
        elif len(result.faces) > 1:
            # Faces alone already suggest another person: look closer
            self._burst_until = now + self.p.burst_s

        visible = not self.dark and (
            bool(result.faces)
            or (
                self._last_objects_check is not None
                and now - self._last_objects_check <= self.p.objects_every_s
                and any(d.area >= self.p.present_person_area for d in self._last_persons)
            )
        )
        return visible, findings

    def _signals(self, r: FrameResult) -> dict[str, list[Detection]]:
        persons = [d for d in r.of("person") if d.area >= self.p.other_person_min_area]
        # Another person: two faces, or two people (one may be turned away, so
        # the face detector misses them; person boxes still count)
        multiple = r.faces if len(r.faces) >= 2 else (persons if len(persons) >= 2 else [])
        return {
            "multiple_people": multiple,
            "phone": r.of("cell phone"),
            "laptop": r.of("laptop"),
        }

    def _update(self, kind: str, dets: list[Detection], now: float, frame_index: int) -> list[Finding]:
        t = self._tracks[kind]
        hit = bool(dets)
        t.hits.append(hit)
        if hit:
            conf = max(d.score for d in dets)
            if t.best is None or conf > t.best[0]:
                t.best = (conf, frame_index, dets)
        if sum(t.hits) < self.p.confirm_hits or t.best is None:
            if not any(t.hits):
                t.best = None
            return []
        if t.last_flag_at is not None and now - t.last_flag_at < self.p.flag_cooldown_s:
            return []
        conf, frame, best_dets = t.best
        t.last_flag_at = now
        t.best = None
        t.hits.clear()
        flag_type, severity, description = FLAGS[kind]
        with_photo = self._photos < self.p.max_photos
        if with_photo:
            self._photos += 1
        return [Finding(kind, flag_type, severity, description, conf, best_dets, frame, with_photo)]

