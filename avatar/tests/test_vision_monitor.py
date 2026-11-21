"""Sampling and confirmation rules for camera checks (agents/vision_monitor.py)."""

from agents.vision import Detection, FrameResult
from agents.vision_monitor import VisionMonitor

FACE = Detection("face", 0.9, (0.4, 0.2, 0.6, 0.5))
FACE2 = Detection("face", 0.8, (0.05, 0.3, 0.2, 0.5))
ME = Detection("person", 0.9, (0.2, 0.1, 0.8, 1.0))
OTHER = Detection("person", 0.8, (0.0, 0.3, 0.2, 1.0))
POSTER = Detection("person", 0.6, (0.9, 0.0, 0.95, 0.1))  # tiny: ignored as "another person"
PHONE = Detection("cell phone", 0.4, (0.7, 0.3, 0.75, 0.4))


def frame(*dets, brightness=120.0):
    faces = [d for d in dets if d.label == "face"]
    return FrameResult(faces=faces, objects=[d for d in dets if d.label != "face"], brightness=brightness)


def test_schedule_faces_every_2s_objects_every_4s_and_bursts():
    m = VisionMonitor()
    assert m.wants_frame(0) and m.wants_objects(0)
    m.observe(0, frame(FACE, ME), True, 0)
    assert not m.wants_frame(1) and m.wants_frame(2)
    assert not m.wants_objects(2) and m.wants_objects(4)
    # Something suspicious: objects on every check for 10 s
    m.observe(4, frame(FACE, ME, PHONE), True, 1)
    assert m.wants_objects(6)
    m.observe(16, frame(FACE, ME), True, 2)
    assert not m.wants_objects(18)


def test_phone_needs_two_of_three_checks_and_keeps_the_best_frame():
    m = VisionMonitor()
    assert m.observe(0, frame(FACE, ME, PHONE), True, 0)[1] == []
    strong = Detection("cell phone", 0.6, PHONE.box)
    visible, found = m.observe(2, frame(FACE, ME, strong), True, 1)
    assert visible and [f.kind for f in found] == ["phone"]
    f = found[0]
    assert (f.flag_type, f.confidence, f.frame_index, f.with_photo) == ("phone_detected", 0.6, 1, True)

    # One-off glimpses never confirm
    m2 = VisionMonitor()
    for t, dets in ((0, (FACE, ME, PHONE)), (2, (FACE, ME)), (4, (FACE, ME)), (6, (FACE, ME, PHONE))):
        assert m2.observe(t, frame(*dets), True, t)[1] == []


def test_cooldown_and_photo_limit():
    m = VisionMonitor()
    times = []
    for t in range(0, 120, 2):
        times += [t for _ in m.observe(t, frame(FACE, ME, PHONE), True, t)[1]]
    assert len(times) == 4 and all(b - a >= 30 for a, b in zip(times, times[1:]))

    m = VisionMonitor()
    m.p = m.p.__class__(max_photos=1)
    found = []
    for t in range(0, 200, 2):
        found += m.observe(t, frame(FACE, ME, PHONE), True, t)[1]
    assert found[0].with_photo and not any(f.with_photo for f in found[1:])


def test_another_person_by_face_or_by_body():
    m = VisionMonitor()
    m.observe(0, frame(FACE, FACE2, ME), True, 0)
    assert [f.kind for f in m.observe(2, frame(FACE, FACE2, ME), True, 1)[1]] == ["multiple_people"]

    # Turned away (no second face) but a second body in view
    m = VisionMonitor()
    m.observe(0, frame(FACE, ME, OTHER), True, 0)
    assert [f.kind for f in m.observe(2, frame(FACE, ME, OTHER), True, 1)[1]] == ["multiple_people"]

    # A tiny figure in the background (poster) is not another person
    m = VisionMonitor()
    for t in (0, 2, 4):
        assert m.observe(t, frame(FACE, ME, POSTER), True, t)[1] == []


def test_presence():
    m = VisionMonitor()
    assert m.observe(0, frame(FACE, ME), True, 0)[0]
    # Head turned: no face, but a big person box from the last object check
    assert m.observe(2, frame(), False, 1)[0]
    # Nobody at all
    assert not m.observe(4, frame(), True, 2)[0]
    # Too dark (or covered) is not "in view", even if something is detected
    assert not m.observe(6, frame(FACE, brightness=10), True, 3)[0]
    assert m.dark


def test_every_flag_kind_has_a_candidate_notice():
    from agents.vision_monitor import CANDIDATE_NOTICES, FLAGS

    assert set(CANDIDATE_NOTICES) == set(FLAGS)
    for title, message in CANDIDATE_NOTICES.values():
        assert title and "recorded for the hiring team" in message
