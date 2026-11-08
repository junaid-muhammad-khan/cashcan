"""Object classifier: which of the 3 physical bins does this item belong in? (organics / cans / waste)

Runs ml/models/mobilenetv2_cashcan.onnx with the SAME preprocessing as ml/scripts/train.py and predict.py
(224x224 bilinear via PIL, ImageNet mean/std). On the RK3582 NPU, convert the model to RKNN (ml/scripts/convert_rknn.py)
and swap this class; the controller only needs `probs(frame) -> {bin: probability}`.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
IMG = 224
DEFAULT_MODEL_DIR = Path(__file__).resolve().parents[2] / "ml" / "models"


def preprocess(frame_bgr: np.ndarray) -> np.ndarray:
    from PIL import Image  # PIL's bilinear resize matches training exactly; cv2's differs slightly

    rgb = frame_bgr[:, :, ::-1]
    img = Image.fromarray(np.ascontiguousarray(rgb)).resize((IMG, IMG), Image.BILINEAR)
    arr = (np.asarray(img, dtype=np.float32) / 255.0 - MEAN) / STD
    return arr.transpose(2, 0, 1)[None].astype(np.float32)


def softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - np.max(x))
    return e / e.sum()


class OnnxClassifier:
    def __init__(self, model: str | Path | None = None, classes: list[str] | None = None):
        import onnxruntime as ort

        model = Path(model) if model else DEFAULT_MODEL_DIR / "mobilenetv2_cashcan.onnx"
        opts = ort.SessionOptions()
        opts.log_severity_level = 3
        self._sess = ort.InferenceSession(str(model), opts, providers=["CPUExecutionProvider"])
        self._in = self._sess.get_inputs()[0].name
        self.classes = classes or json.loads((model.parent / "classes.json").read_text())

    def probs(self, frame_bgr: np.ndarray) -> dict[str, float]:
        logits = self._sess.run(None, {self._in: preprocess(frame_bgr)})[0][0]
        return dict(zip(self.classes, softmax(logits).tolist()))


def decide(prob_list: list[dict[str, float]], min_confidence: float, fallback: str = "waste") -> tuple[str, float, str]:
    """Average several looks, then pick the bin. Returns (bin, confidence, reason).
    Not sure enough -> the fallback bin (waste): an unsure item must not be rewarded or put in the wrong recycling stream."""
    classes = prob_list[0].keys()
    avg = {c: float(np.mean([p[c] for p in prob_list])) for c in classes}
    best = max(avg, key=avg.get)
    if avg[best] < min_confidence:
        return fallback, avg[best], "low_confidence"
    return best, avg[best], "ok"
