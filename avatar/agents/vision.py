"""Camera checks on the candidate's video, run by the voice agent on our server.

Two small TensorFlow Lite models (agents/models/README.md), run with LiteRT on
CPU, no GPU:

- BlazeFace (short range), 230 KB: faces, to count people facing the camera.
- EfficientDet-Lite0 (int8), 4.6 MB: COCO objects; we use person, cell phone
  and laptop.

Neither model has its post-processing built in, so anchors, box decoding and
non-maximum suppression are done here with numpy.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).parent / "models"
FACE_MODEL = MODELS_DIR / "blaze_face_short_range.tflite"
OBJECT_MODEL = MODELS_DIR / "efficientdet_lite0.tflite"

FACE_MIN_SCORE = 0.5
# A plain grey frame scores up to 0.45; frames must also agree over time (agents/vision_monitor.py)
OBJECT_MIN_SCORE = 0.5
OBJECTS_OF_INTEREST = {"person", "cell phone", "laptop"}
# A phone is a few pixels once a webcam frame is shrunk to 320x320, so phones
# are also looked for in 4 overlapping tiles, where they score lower but real
PHONE_MIN_SCORE = 0.3
TILE_OVERLAP = 0.15


@dataclass(frozen=True)
class Detection:
    label: str
    score: float
    # Normalized to the frame: 0..1, (x0, y0) top left
    box: tuple[float, float, float, float]

    @property
    def area(self) -> float:
        x0, y0, x1, y1 = self.box
        return max(0.0, x1 - x0) * max(0.0, y1 - y0)

    def as_dict(self) -> dict:
        return {"label": self.label, "score": round(self.score, 3), "box": [round(v, 4) for v in self.box]}


@dataclass(frozen=True)
class FrameResult:
    faces: list[Detection]
    objects: list[Detection]
    brightness: float  # mean luminance, 0..255

    def of(self, label: str) -> list[Detection]:
        return [d for d in self.objects if d.label == label]


# =============================================================================
# Geometry
# =============================================================================


def iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def nms(boxes: np.ndarray, scores: np.ndarray, iou_threshold: float, limit: int = 20) -> list[int]:
    """Indices of boxes kept, highest score first. boxes: [N, 4] as x0, y0, x1, y1."""
    order = np.argsort(-scores)
    keep: list[int] = []
    while order.size and len(keep) < limit:
        i = int(order[0])
        keep.append(i)
        rest = order[1:]
        if not rest.size:
            break
        x0 = np.maximum(boxes[i, 0], boxes[rest, 0])
        y0 = np.maximum(boxes[i, 1], boxes[rest, 1])
        x1 = np.minimum(boxes[i, 2], boxes[rest, 2])
        y1 = np.minimum(boxes[i, 3], boxes[rest, 3])
        inter = np.clip(x1 - x0, 0, None) * np.clip(y1 - y0, 0, None)
        area_i = (boxes[i, 2] - boxes[i, 0]) * (boxes[i, 3] - boxes[i, 1])
        area_r = (boxes[rest, 2] - boxes[rest, 0]) * (boxes[rest, 3] - boxes[rest, 1])
        overlap = inter / np.maximum(area_i + area_r - inter, 1e-9)
        order = rest[overlap <= iou_threshold]
    return keep


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -50, 50)))


# =============================================================================
# Anchors
# =============================================================================


def blazeface_anchors() -> np.ndarray:
    """MediaPipe BlazeFace short range: 128x128 input, strides 8,16,16,16, two
    anchors per cell per layer (layers with the same stride share a grid).
    Returns [896, 2] anchor centres (x, y), normalized; anchor size is fixed at 1."""
    anchors = []
    for stride, per_cell in ((8, 2), (16, 6)):
        grid = 128 // stride
        for y in range(grid):
            for x in range(grid):
                for _ in range(per_cell):
                    anchors.append(((x + 0.5) / grid, (y + 0.5) / grid))
    return np.asarray(anchors, dtype=np.float32)


def efficientdet_anchors(size: int = 320) -> np.ndarray:
    """EfficientDet anchors (AutoML / TF Lite Model Maker): levels 3-7, three
    scales per octave, aspect ratios 1, 2, 0.5, anchor scale 4. Order: level,
    then row, column, then (scale, aspect). Returns [N, 4] as yc, xc, h, w in pixels."""
    anchors = []
    configs = [(octave / 3, aspect) for octave in range(3) for aspect in (1.0, 2.0, 0.5)]
    for level in range(3, 8):
        stride = 2**level
        grid = int(np.ceil(size / stride))
        for y in range(grid):
            for x in range(grid):
                yc, xc = (y + 0.5) * stride, (x + 0.5) * stride
                for octave_scale, aspect in configs:
                    base = 4.0 * stride * 2**octave_scale
                    h = base / np.sqrt(aspect)
                    w = base * np.sqrt(aspect)
                    anchors.append((yc, xc, h, w))
    return np.asarray(anchors, dtype=np.float32)


# =============================================================================
# Models
# =============================================================================


class VisionModels:
    """Both detectors, loaded once per process. Thread-safe (one call at a time)."""

    def __init__(self, face_model: Path = FACE_MODEL, object_model: Path = OBJECT_MODEL):
        from ai_edge_litert.interpreter import Interpreter

        self._lock = threading.Lock()
        self._face = Interpreter(model_path=str(face_model), num_threads=1)
        self._face.allocate_tensors()
        self._objects = Interpreter(model_path=str(object_model), num_threads=1)
        self._objects.allocate_tensors()
        self._face_anchors = blazeface_anchors()
        self._object_anchors = efficientdet_anchors()
        self._labels = _read_labels(object_model)

        out = {d["name"]: d for d in self._objects.get_output_details()}
        # [1, N, 90] class scores and [1, N, 4] box encodings
        self._obj_scores = next(d["index"] for d in out.values() if d["shape"][-1] != 4)
        self._obj_boxes = next(d["index"] for d in out.values() if d["shape"][-1] == 4)
        fout = {d["name"]: d["index"] for d in self._face.get_output_details()}
        self._face_reg, self._face_cls = fout["regressors"], fout["classificators"]

    def analyze(self, rgb: np.ndarray, objects: bool = True) -> FrameResult:
        """rgb: [H, W, 3] uint8. objects=False: faces only (the cheap check)."""
        brightness = float(rgb.mean()) if rgb.size else 0.0
        image = Image.fromarray(rgb)
        with self._lock:
            faces = self._detect_faces(image)
            found = self._detect_objects_tiled(image) if objects else []
        return FrameResult(faces=faces, objects=found, brightness=brightness)

    def _detect_objects_tiled(self, image: Image.Image) -> list[Detection]:
        """Whole frame for people and laptops; whole frame plus 4 tiles for phones."""
        found = [d for d in self._detect_objects(image) if d.label != "cell phone" or d.score >= OBJECT_MIN_SCORE]
        phones = [d for d in found if d.label == "cell phone"]
        found = [d for d in found if d.label != "cell phone"]

        w, h = image.size
        tw, th = w * (0.5 + TILE_OVERLAP / 2), h * (0.5 + TILE_OVERLAP / 2)
        for tx0 in (0.0, w - tw):
            for ty0 in (0.0, h - th):
                tile = image.crop((int(tx0), int(ty0), int(tx0 + tw), int(ty0 + th)))
                for d in self._detect_objects(tile, labels={"cell phone"}, min_score=PHONE_MIN_SCORE):
                    x0, y0, x1, y1 = d.box
                    box = ((tx0 + x0 * tw) / w, (ty0 + y0 * th) / h, (tx0 + x1 * tw) / w, (ty0 + y1 * th) / h)
                    phones.append(Detection(d.label, d.score, box))
        if phones:
            boxes = np.asarray([d.box for d in phones], dtype=np.float32)
            scores = np.asarray([d.score for d in phones], dtype=np.float32)
            found += [phones[i] for i in nms(boxes, scores, 0.3)]
        return found

    def _detect_faces(self, image: Image.Image) -> list[Detection]:
        x = np.asarray(image.resize((128, 128), Image.BILINEAR), dtype=np.float32) / 127.5 - 1.0
        self._face.set_tensor(self._face.get_input_details()[0]["index"], x[None])
        self._face.invoke()
        reg = self._face.get_tensor(self._face_reg)[0]  # [896, 16]: x, y, w, h, 6 keypoints
        scores = _sigmoid(self._face.get_tensor(self._face_cls)[0, :, 0])
        mask = scores >= FACE_MIN_SCORE
        if not mask.any():
            return []
        reg, scores, anchors = reg[mask], scores[mask], self._face_anchors[mask]
        xc = reg[:, 0] / 128 + anchors[:, 0]
        yc = reg[:, 1] / 128 + anchors[:, 1]
        w, h = reg[:, 2] / 128, reg[:, 3] / 128
        boxes = np.stack([xc - w / 2, yc - h / 2, xc + w / 2, yc + h / 2], axis=1).clip(0, 1)
        return [
            Detection("face", float(scores[i]), tuple(float(v) for v in boxes[i]))
            for i in nms(boxes, scores, 0.3)
        ]

    def _detect_objects(
        self, image: Image.Image, labels: set[str] = OBJECTS_OF_INTEREST, min_score: float = OBJECT_MIN_SCORE
    ) -> list[Detection]:
        x = np.asarray(image.resize((320, 320), Image.BILINEAR), dtype=np.uint8)
        self._objects.set_tensor(self._objects.get_input_details()[0]["index"], x[None])
        self._objects.invoke()
        probs = self._objects.get_tensor(self._obj_scores)[0]  # [N, 90], already 0..1
        enc = self._objects.get_tensor(self._obj_boxes)[0]  # [N, 4]: ty, tx, th, tw

        wanted = [i for i, name in enumerate(self._labels) if name in labels]
        scores_all = probs[:, wanted]
        best = scores_all.argmax(axis=1)
        scores = scores_all[np.arange(len(best)), best]
        mask = scores >= min_score
        if not mask.any():
            return []
        a, e, s, cls = self._object_anchors[mask], enc[mask], scores[mask], best[mask]
        yc = e[:, 0] * a[:, 2] + a[:, 0]
        xc = e[:, 1] * a[:, 3] + a[:, 1]
        h = np.exp(e[:, 2]) * a[:, 2]
        w = np.exp(e[:, 3]) * a[:, 3]
        boxes = (np.stack([xc - w / 2, yc - h / 2, xc + w / 2, yc + h / 2], axis=1) / 320).clip(0, 1)

        found: list[Detection] = []
        for c in np.unique(cls):
            idx = np.where(cls == c)[0]
            label = self._labels[wanted[int(c)]]
            for k in nms(boxes[idx], s[idx], 0.5):
                i = idx[k]
                found.append(Detection(label, float(s[i]), tuple(float(v) for v in boxes[i])))
        return found


def _read_labels(model: Path) -> list[str]:
    import zipfile

    with zipfile.ZipFile(model) as z:
        return z.read("labels.txt").decode().splitlines()


_models: VisionModels | None = None
_models_lock = threading.Lock()


def get_models() -> VisionModels:
    """Shared per process (loaded in the agent's prewarm)."""
    global _models
    with _models_lock:
        if _models is None:
            _models = VisionModels()
        return _models
