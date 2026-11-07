"""Face detection + embedding. Wraps InsightFace so the rest of the app (and tests)
only deal with plain data."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import cv2
import numpy as np

from . import config
from .liveness import turn_ratio


@dataclass
class FaceResult:
    embedding: np.ndarray  # L2-normalised, shape (512,)
    det_score: float
    box: tuple[int, int, int, int]  # x1, y1, x2, y2
    sharpness: float
    turn: float | None = None  # head-turn ratio, see liveness.turn_ratio; None if unavailable


class FaceEngine(Protocol):
    def analyse(self, image_bgr: np.ndarray) -> list[FaceResult]: ...


class QualityError(ValueError):
    """Frame is unusable. The message is safe to show the user."""


def decode_image(data: bytes) -> np.ndarray:
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise QualityError("Could not read the image.")
    return img


def pick_face(faces: list[FaceResult]) -> FaceResult:
    """Largest face wins (the person standing at the bin)."""
    if not faces:
        raise QualityError("No face found. Look at the camera.")
    return max(faces, key=lambda f: (f.box[2] - f.box[0]) * (f.box[3] - f.box[1]))


def check_quality(face: FaceResult) -> None:
    w, h = face.box[2] - face.box[0], face.box[3] - face.box[1]
    if face.det_score < config.MIN_DET_SCORE:
        raise QualityError("Face not clear enough. Improve the lighting.")
    if min(w, h) < config.MIN_FACE_PX:
        raise QualityError("Move closer to the camera.")
    if face.sharpness < config.MIN_SHARPNESS:
        raise QualityError("Image is blurry. Hold still.")


class InsightFaceEngine:
    def __init__(self, model: str = "buffalo_s", det_size: int = 320):
        from insightface.app import FaceAnalysis  # heavy import, keep lazy

        self._app = FaceAnalysis(name=model, providers=["CPUExecutionProvider"])
        self._app.prepare(ctx_id=-1, det_size=(det_size, det_size))

    def analyse(self, image_bgr: np.ndarray) -> list[FaceResult]:
        out: list[FaceResult] = []
        for f in self._app.get(image_bgr):
            x1, y1, x2, y2 = (int(v) for v in f.bbox)
            x1, y1 = max(x1, 0), max(y1, 0)
            crop = image_bgr[y1:max(y2, y1 + 1), x1:max(x2, x1 + 1)]
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            sharp = float(cv2.Laplacian(gray, cv2.CV_64F).var())
            emb = np.asarray(f.normed_embedding, dtype=np.float32)
            turn = turn_ratio(np.asarray(f.kps)) if getattr(f, "kps", None) is not None else None
            out.append(FaceResult(emb, float(f.det_score), (x1, y1, x2, y2), sharp, turn))
        return out
