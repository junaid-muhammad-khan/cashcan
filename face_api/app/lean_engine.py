"""Face engine without the insightface package: onnxruntime + OpenCV + numpy only.

Runs the same two buffalo_s ONNX models InsightFaceEngine uses (det_500m detector, w600k_mbf recognizer) with the same
pre-processing, so embeddings match (checked in tests/ and EVAL notes). It exists because insightface pulls scipy, scikit-image,
matplotlib, onnx... which push the Python bundle past Vercel's 500 MB function limit; this one is well under.
No head-pose model, so FaceResult.yaw is always None (diagnostic only).
"""
from __future__ import annotations

import os
from pathlib import Path

import cv2
import numpy as np

from .face_engine import FaceResult, face_sharpness
from .liveness import turn_ratio

MODEL_DIR = Path(os.environ.get("CASHCAN_MODEL_DIR", Path(__file__).resolve().parent.parent / "models"))
DETECTOR, RECOGNIZER = "det_500m.onnx", "w600k_mbf.onnx"

# Standard ArcFace 112x112 landmark template (left eye, right eye, nose, left mouth, right mouth)
ARCFACE_DST = np.array([[38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366],
                        [41.5493, 92.3655], [70.7299, 92.2041]], dtype=np.float32)
STRIDES, NUM_ANCHORS = (8, 16, 32), 2


def models_available(model_dir: Path = MODEL_DIR) -> bool:
    return (model_dir / DETECTOR).exists() and (model_dir / RECOGNIZER).exists()


def _similarity(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """Least-squares similarity transform (Umeyama), 2x3, same result as skimage SimilarityTransform.estimate."""
    n = src.shape[0]
    sm, dm = src.mean(0), dst.mean(0)
    s, d = src - sm, dst - dm
    cov = d.T @ s / n
    u, sig, vt = np.linalg.svd(cov)
    r = np.eye(2)
    if np.linalg.det(cov) < 0:
        r[1, 1] = -1
    rot = u @ r @ vt
    scale = (sig * np.diag(r)).sum() / s.var(0).sum()
    t = dm - scale * rot @ sm
    return np.hstack([scale * rot, t[:, None]]).astype(np.float32)


def _nms(dets: np.ndarray, thresh: float) -> list[int]:
    x1, y1, x2, y2, sc = dets[:, 0], dets[:, 1], dets[:, 2], dets[:, 3], dets[:, 4]
    areas = (x2 - x1 + 1) * (y2 - y1 + 1)
    order, keep = sc.argsort()[::-1], []
    while order.size:
        i = order[0]
        keep.append(int(i))
        xx1, yy1 = np.maximum(x1[i], x1[order[1:]]), np.maximum(y1[i], y1[order[1:]])
        xx2, yy2 = np.minimum(x2[i], x2[order[1:]]), np.minimum(y2[i], y2[order[1:]])
        inter = np.maximum(0.0, xx2 - xx1 + 1) * np.maximum(0.0, yy2 - yy1 + 1)
        order = order[1:][inter / (areas[i] + areas[order[1:]] - inter) <= thresh]
    return keep


class LeanEngine:
    def __init__(self, det_size: int = 320, det_thresh: float = 0.5, nms_thresh: float = 0.4,
                 model_dir: Path = MODEL_DIR):
        import onnxruntime as ort

        opts = ort.SessionOptions()
        opts.log_severity_level = 3
        mk = lambda name: ort.InferenceSession(str(model_dir / name), opts, providers=["CPUExecutionProvider"])
        self._det, self._rec = mk(DETECTOR), mk(RECOGNIZER)
        self._det_in, self._rec_in = self._det.get_inputs()[0].name, self._rec.get_inputs()[0].name
        self.size, self.det_thresh, self.nms_thresh = det_size, det_thresh, nms_thresh
        self._anchors: dict[tuple[int, int, int], np.ndarray] = {}

    def _centers(self, h: int, w: int, stride: int) -> np.ndarray:
        key = (h, w, stride)
        if key not in self._anchors:
            c = np.stack(np.mgrid[:h, :w][::-1], axis=-1).astype(np.float32).reshape(-1, 2) * stride
            self._anchors[key] = np.repeat(c, NUM_ANCHORS, axis=0)
        return self._anchors[key]

    def _detect(self, img: np.ndarray):
        size = self.size
        ratio = img.shape[0] / img.shape[1]
        nw, nh = (size, int(size * ratio)) if ratio <= 1 else (int(size / ratio), size)
        scale = nh / img.shape[0]
        canvas = np.zeros((size, size, 3), np.uint8)
        canvas[:nh, :nw] = cv2.resize(img, (nw, nh))
        blob = cv2.dnn.blobFromImage(canvas, 1.0 / 128, (size, size), (127.5, 127.5, 127.5), swapRB=True)
        outs = self._det.run(None, {self._det_in: blob})
        scores, boxes, kpss = [], [], []
        for idx, stride in enumerate(STRIDES):
            s, b, k = outs[idx][:, 0], outs[idx + 3] * stride, outs[idx + 6] * stride
            c = self._centers(size // stride, size // stride, stride)
            keep = np.where(s >= self.det_thresh)[0]
            if not keep.size:
                continue
            c, s, b, k = c[keep], s[keep], b[keep], k[keep]
            boxes.append(np.hstack([c - b[:, :2], c + b[:, 2:]]))
            kpss.append((c[:, None, :] + k.reshape(-1, 5, 2)))
            scores.append(s)
        if not scores:
            return []
        sc, bx, kp = np.concatenate(scores), np.concatenate(boxes) / scale, np.concatenate(kpss) / scale
        dets = np.hstack([bx, sc[:, None]]).astype(np.float32)
        return [(bx[i], float(sc[i]), kp[i]) for i in _nms(dets, self.nms_thresh)]

    def _embed(self, img: np.ndarray, kps: np.ndarray) -> np.ndarray:
        m = _similarity(kps.astype(np.float32), ARCFACE_DST)
        crop = cv2.warpAffine(img, m, (112, 112), borderValue=0.0)
        blob = cv2.dnn.blobFromImage(crop, 1.0 / 127.5, (112, 112), (127.5, 127.5, 127.5), swapRB=True)
        e = self._rec.run(None, {self._rec_in: blob})[0][0].astype(np.float32)
        return e / np.linalg.norm(e)

    def analyse(self, image_bgr: np.ndarray) -> list[FaceResult]:
        out: list[FaceResult] = []
        for box, score, kps in self._detect(image_bgr):
            x1, y1, x2, y2 = (int(v) for v in box)
            x1, y1 = max(x1, 0), max(y1, 0)
            out.append(FaceResult(self._embed(image_bgr, kps), score, (x1, y1, x2, y2),
                                  face_sharpness(image_bgr, (x1, y1, x2, y2)), turn_ratio(kps), None))
        return out
