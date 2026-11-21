"""The camera-check models load and their decoding matches their outputs."""

import numpy as np

from agents.vision import (
    VisionModels,
    blazeface_anchors,
    efficientdet_anchors,
    iou,
    nms,
)


def test_anchor_counts_match_the_models():
    m = VisionModels()
    assert len(blazeface_anchors()) == m._face.get_output_details()[0]["shape"][1] == 896
    boxes = next(d for d in m._objects.get_output_details() if d["shape"][-1] == 4)
    assert len(efficientdet_anchors()) == boxes["shape"][1] == 19206
    assert {"person", "cell phone", "laptop"} <= set(m._labels)


def test_blank_frames_find_nothing_and_report_brightness():
    m = VisionModels()
    for value in (0, 128, 255):
        r = m.analyze(np.full((480, 640, 3), value, np.uint8))
        assert r.faces == [] and r.objects == []
        assert round(r.brightness) == value


def test_nms_and_iou():
    boxes = np.array([[0, 0, 1, 1], [0.05, 0.05, 1, 1], [2, 2, 3, 3]], dtype=np.float32)
    assert nms(boxes, np.array([0.9, 0.8, 0.7], dtype=np.float32), 0.5) == [0, 2]
    assert iou((0, 0, 1, 1), (0, 0, 1, 1)) == 1.0 and iou((0, 0, 1, 1), (2, 2, 3, 3)) == 0.0
