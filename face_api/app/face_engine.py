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
    yaw: float | None = None  # InsightFace head yaw in degrees (diagnostic only; not used for decisions)


class FaceEngine(Protocol):
    def analyse(self, image_bgr: np.ndarray) -> list[FaceResult]: ...


SHARPNESS_NORM_PX = 112  # the size the recognition model actually sees


def face_sharpness(image_bgr: np.ndarray, box: tuple[int, int, int, int]) -> float:
    """Variance of the Laplacian of the face crop, measured at a fixed 112x112 size and a fixed contrast.

    The raw variance depends on how many pixels the face covers: the same sharp photo scores ~1000 at a
    100 px face and ~15 at a 560 px face, so a fixed limit wrongly rejects close-up faces. Resizing to the
    model's input size first makes the number comparable at any distance while still dropping with real blur.
    Standardising the contrast stops dim or side-lit faces (low contrast, not blur) from reading as blurry: the same sharp photo
    scored 34 to 530 under different lighting before, and about 300-430 after."""
    x1, y1, x2, y2 = box
    crop = image_bgr[max(y1, 0):max(y2, y1 + 1), max(x1, 0):max(x2, x1 + 1)]
    if crop.size == 0:
        return 0.0
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, (SHARPNESS_NORM_PX, SHARPNESS_NORM_PX), interpolation=cv2.INTER_AREA).astype(np.float32)
    gray = (gray - gray.mean()) / (gray.std() + 1e-3) * 50.0 + 128.0   # same contrast whatever the lighting
    return float(np.var(cv2.Laplacian(gray, cv2.CV_32F)))


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


def check_quality(face: FaceResult, identification: bool = False) -> None:
    """Raise QualityError if the frame is unusable. identification=False is the strict enrollment tier; True is the lenient
    tier for recognising someone (see config for why they differ)."""
    min_det = config.ID_MIN_DET_SCORE if identification else config.MIN_DET_SCORE
    min_px = config.ID_MIN_FACE_PX if identification else config.MIN_FACE_PX
    min_sharp = config.ID_MIN_SHARPNESS if identification else config.MIN_SHARPNESS
    w, h = face.box[2] - face.box[0], face.box[3] - face.box[1]
    if face.det_score < min_det:
        raise QualityError("Face not clear enough. Improve the lighting.")
    if min(w, h) < min_px:
        raise QualityError("Move closer to the camera.")
    if face.sharpness < min_sharp:
        raise QualityError("Image is blurry. Hold still.")


class InsightFaceEngine:
    def __init__(self, model: str = "buffalo_s", det_size: int = 320, modules: list[str] | None = None):
        """modules=None loads the whole pack. ["detection", "recognition"] skips the 144 MB pose model
        (about 2x faster); FaceResult.yaw is then None, which only diagnostics use."""
        from insightface.app import FaceAnalysis  # heavy import, keep lazy
        import warnings

        # insightface calls a scikit-image function that is deprecated; harmless, but it looks like an error
        warnings.filterwarnings("ignore", message=".*estimate.*deprecated.*", category=FutureWarning)

        self._app = FaceAnalysis(name=model, providers=["CPUExecutionProvider"], allowed_modules=modules)
        self._app.prepare(ctx_id=-1, det_size=(det_size, det_size))

    def analyse(self, image_bgr: np.ndarray) -> list[FaceResult]:
        out: list[FaceResult] = []
        for f in self._app.get(image_bgr):
            x1, y1, x2, y2 = (int(v) for v in f.bbox)
            x1, y1 = max(x1, 0), max(y1, 0)
            sharp = face_sharpness(image_bgr, (x1, y1, x2, y2))
            emb = np.asarray(f.normed_embedding, dtype=np.float32)
            turn = turn_ratio(np.asarray(f.kps)) if getattr(f, "kps", None) is not None else None
            pose = getattr(f, "pose", None)
            yaw = float(pose[1]) if pose is not None else None
            out.append(FaceResult(emb, float(f.det_score), (x1, y1, x2, y2), sharp, turn, yaw))
        return out
