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

        if model is None:  # the INT8 model is the Pi default (3.4x smaller, faster, ~0.4 points less accurate: see ml/QUANTIZATION.md); FP32 if it is missing
            int8 = DEFAULT_MODEL_DIR / "mobilenetv2_cashcan_int8.onnx"
            model = int8 if int8.exists() else DEFAULT_MODEL_DIR / "mobilenetv2_cashcan.onnx"
        model = Path(model)
        opts = ort.SessionOptions()
        opts.log_severity_level = 3
        self._sess = ort.InferenceSession(str(model), opts, providers=["CPUExecutionProvider"])
        self._in = self._sess.get_inputs()[0].name
        self.classes = classes or json.loads((model.parent / "classes.json").read_text())

    def probs(self, frame_bgr: np.ndarray) -> dict[str, float]:
        logits = self._sess.run(None, {self._in: preprocess(frame_bgr)})[0][0]
        return dict(zip(self.classes, softmax(logits).tolist()))


def average_probs(prob_list: list[dict[str, float]]) -> dict[str, float]:
    return {c: float(np.mean([p[c] for p in prob_list])) for c in prob_list[0]}


def decide(prob_list: list[dict[str, float]], min_confidence: float, fallback: str = "waste") -> tuple[str, float, str]:
    """Average several looks, then pick the bin. Returns (bin, confidence, reason).
    Not sure enough -> the fallback bin (waste): an unsure item must not be rewarded or put in the wrong recycling stream."""
    classes = prob_list[0].keys()
    avg = {c: float(np.mean([p[c] for p in prob_list])) for c in classes}
    best = max(avg, key=avg.get)
    if avg[best] < min_confidence:
        return fallback, avg[best], "low_confidence"
    return best, avg[best], "ok"


class TeachableClassifier(OnnxClassifier):
    """The classifier plus on-device teaching: show it an item, say what it really is, and from then on items that look like what you taught are
    judged by that, not only by the public-photo training. It works on the model's own 1280-number picture features (a nearest-neighbour check),
    so teaching is instant and needs no retraining. It only overrides the model when an item looks close to something taught, and it never affects items
    that look nothing like what you taught (measured: items shown again 78% -> 100% right; other cans +15 points; other waste unchanged).

    Needs the FP32 model (the features come from inside it). Teaching is saved to `store` (an .npz file) and each taught photo to `photos/<label>/`.
    """

    LO, HI, TEMP = 0.60, 0.90, 20.0   # similarity ramp: below LO the taught examples are ignored, at HI they decide
    DUP = 0.985                        # a new picture this similar to one already taught under the same label adds nothing: it is skipped
    MAX_PER_LABEL = 60                 # keep the newest; more only slows matching and lets one bad example linger

    def __init__(self, model=None, classes=None, store: str | Path | None = None, photos: str | Path | None = None):
        import onnx
        from onnx import TensorProto, helper
        import onnxruntime as ort

        if model is None:
            model = DEFAULT_MODEL_DIR / "mobilenetv2_cashcan.onnx"          # FP32: the INT8 file has no usable feature output
        model = Path(model)
        proto = onnx.load(str(model))
        gemm = [n for n in proto.graph.node if n.op_type == "Gemm"][-1]      # the final classifier layer; its input is the pooled features
        proto.graph.output.append(helper.make_tensor_value_info(gemm.input[0], TensorProto.FLOAT, [None, 1280]))
        opts = ort.SessionOptions()
        opts.log_severity_level = 3
        self._sess = ort.InferenceSession(proto.SerializeToString(), opts, providers=["CPUExecutionProvider"])
        self._in = self._sess.get_inputs()[0].name
        self.classes = classes or json.loads((model.parent / "classes.json").read_text())
        self.store = Path(store or Path.home() / ".cashcan" / "taught.npz").expanduser()
        self.photos = Path(photos or Path.home() / ".cashcan" / "taught_photos").expanduser()
        self.vecs = np.zeros((0, 1280), np.float32)
        self.labels: list[str] = []
        self.last_added = True
        self._load()

    def _load(self) -> None:
        try:
            d = np.load(self.store, allow_pickle=False)
            self.vecs, self.labels = d["vecs"].astype(np.float32), [str(x) for x in d["labels"]]
        except (OSError, ValueError, KeyError):
            pass

    def _save(self) -> None:
        try:
            self.store.parent.mkdir(parents=True, exist_ok=True)
            np.savez(self.store, vecs=self.vecs, labels=np.array(self.labels))
        except OSError:
            pass

    def _run(self, frame_bgr: np.ndarray):
        logits, feat = self._sess.run(None, {self._in: preprocess(frame_bgr)})
        f = feat[0] / max(float(np.linalg.norm(feat[0])), 1e-9)
        return softmax(logits[0]), f.astype(np.float32)

    def probs(self, frame_bgr: np.ndarray) -> dict[str, float]:
        base, f = self._run(frame_bgr)
        if len(self.labels):
            sims = self.vecs @ f
            sc = {c: float(sims[[i for i, l in enumerate(self.labels) if l == c]].max()) for c in set(self.labels)}
            best = max(sc, key=sc.get)
            w = float(np.clip((sc[best] - self.LO) / (self.HI - self.LO), 0.0, 1.0))
            if w > 0:
                taught = np.zeros(len(self.classes), np.float64)
                for c, v in sc.items():
                    taught[self.classes.index(c)] = np.exp(self.TEMP * v)
                base = (1 - w) * base + w * (taught / taught.sum())
        return dict(zip(self.classes, base.tolist()))

    def teach(self, label: str, frame_bgr: np.ndarray) -> int:
        """Remember this picture as an example of `label`. Returns how many examples of that label are stored."""
        if label not in self.classes:
            raise ValueError(f"label must be one of {self.classes}")
        _, f = self._run(frame_bgr)
        same = [i for i, l in enumerate(self.labels) if l == label]
        self.last_added = not (same and float((self.vecs[same] @ f).max()) >= self.DUP)
        if not self.last_added:                       # already knows this view (e.g. a key held down): do not store it again
            return len(same)
        self.vecs = np.vstack([self.vecs, f[None]])
        self.labels.append(label)
        if len(same) + 1 > self.MAX_PER_LABEL:         # drop the oldest example of this label
            drop = same[0]
            self.vecs = np.delete(self.vecs, drop, axis=0)
            del self.labels[drop]
        self._save()
        try:
            import cv2, time as _t

            d = self.photos / label
            d.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(d / f"{_t.strftime('%Y%m%d-%H%M%S')}_{len(self.labels)}.jpg"), frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 92])
        except Exception:
            pass
        return self.labels.count(label)

    def forget_last(self) -> str | None:
        if not self.labels:
            return None
        gone = self.labels.pop()
        self.vecs = self.vecs[:-1]
        self._save()
        return gone

    def clear(self) -> None:
        self.vecs, self.labels = np.zeros((0, 1280), np.float32), []
        self._save()
