# Camera-check models

Used by the voice agent (`agents/vision.py`) on the candidate's video, on our
server, with the LiteRT runtime (`ai-edge-litert`) on CPU. Kept in the repo so
the agent never downloads models at run time (the previous browser models broke
when their download address went away).

| File | What | Source | Size | SHA-256 |
|---|---|---|---|---|
| `blaze_face_short_range.tflite` | Face detector (BlazeFace, short range, float16) | https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite | 229,746 B | `b4578f35940bf5a1a655214a1cce5cab13eba73c1297cd78e1a04c2380b0152f` |
| `efficientdet_lite0.tflite` | Object detector (EfficientDet-Lite0, int8, COCO labels embedded) | https://storage.googleapis.com/mediapipe-models/object_detector/efficientdet_lite0/int8/1/efficientdet_lite0.tflite | 4,602,795 B | `0720bf247bd76e6594ea28fa9c6f7c5242be774818997dbbeffc4da460c723bb` |

Both are Google MediaPipe models, Apache License 2.0.

Neither has its post-processing built in: anchors, box decoding and
non-maximum suppression are in `agents/vision.py`. Checked on real photos
(one person; two people with a phone): faces, people and the phone land in the
right places. Phones are small in a webcam frame, so they are also searched in
four overlapping tiles.
