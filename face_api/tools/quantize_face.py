"""INT8-quantize the face recognizer for the Pi and measure what it costs on LFW verification pairs.

  python -m tools.quantize_face --data DIR      # DIR has data.parquet (all LFW photos, for calibration) and pairs_test.parquet (see tools.eval_lfw)

Calibrates on aligned face crops (no labels needed), then compares FP32 and INT8 on the same crops: embedding agreement, verification
accuracy (same person or not, 2,200 pairs) at the bin's threshold and at the best threshold, true-accept rate at a 0.1% false-accept rate,
file size and latency. Writes models/w600k_mbf_int8.onnx.
"""
from __future__ import annotations

import argparse
import random
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort
import pandas as pd
from onnxruntime.quantization import CalibrationDataReader, QuantFormat, QuantType, quantize_static

from app import config
from app.face_engine import decode_image
from app.lean_engine import LeanEngine, MODEL_DIR, RECOGNIZER


def with_opset(src: Path, version: int = 17) -> Path:
    """Static quantization writes DequantizeLinear nodes with a per-channel `axis`, which needs ONNX opset 13+; this model is older."""
    import onnx
    from onnx import version_converter

    m = onnx.load(str(src))
    if max(o.version for o in m.opset_import if o.domain in ("", "ai.onnx")) >= 13:
        return src
    tmp = src.with_name(src.stem + "_opset.onnx")
    onnx.save(version_converter.convert_version(m, version), str(tmp))
    return tmp


def blob(crop: np.ndarray) -> np.ndarray:
    return ((crop[:, :, ::-1].astype(np.float32) - 127.5) / 127.5).transpose(2, 0, 1)[None]


def crop_of(eng: LeanEngine, data: bytes):
    img = decode_image(data)
    dets = eng._detect(img)
    if not dets:
        return None
    best = max(dets, key=lambda d: d[1])
    return eng.align(img, best[2])


class Reader(CalibrationDataReader):
    def __init__(self, crops, name):
        self._it = iter([{name: blob(c)} for c in crops])

    def get_next(self):
        return next(self._it, None)


def sess(path):
    o = ort.SessionOptions(); o.log_severity_level = 3
    return ort.InferenceSession(str(path), o, providers=["CPUExecutionProvider"])


def embed_all(s, crops):
    name = s.get_inputs()[0].name
    out = np.concatenate([s.run(None, {name: blob(c)})[0] for c in crops]).astype(np.float32)
    return out / np.linalg.norm(out, axis=1, keepdims=True)


def verification(emb_a, emb_b, same):
    sims = (emb_a * emb_b).sum(1)
    thr = np.linspace(-0.2, 0.9, 551)
    accs = [((sims >= t) == same).mean() for t in thr]
    k = int(np.argmax(accs))
    neg = np.sort(sims[~same])[::-1]
    far_t = neg[max(int(len(neg) * 0.001) - 1, 0)]            # threshold that lets 0.1% of different-person pairs through
    return {"acc_at_bin_threshold": ((sims >= config.MATCH_THRESHOLD) == same).mean(), "best_acc": accs[k], "best_threshold": thr[k],
            "tar_at_far_0.1%": (sims[same] > far_t).mean(), "mean_same": sims[same].mean(), "mean_diff": sims[~same].mean()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--n-calib", type=int, default=300)
    ap.add_argument("--out", default=str(MODEL_DIR / "w600k_mbf_int8.onnx"))
    a = ap.parse_args()
    random.seed(0)
    eng = LeanEngine()
    src = MODEL_DIR / RECOGNIZER

    imgs = pd.read_parquet(Path(a.data) / "data.parquet")["image"].tolist()
    random.shuffle(imgs)
    calib = []
    for im in imgs:
        c = crop_of(eng, im["bytes"])
        if c is not None:
            calib.append(c)
        if len(calib) >= a.n_calib:
            break
    print(f"calibrating on {len(calib)} aligned face crops ...")
    name = sess(src).get_inputs()[0].name
    base = with_opset(src)
    quantize_static(str(base), a.out, Reader(calib, name), quant_format=QuantFormat.QDQ, per_channel=True,
                    activation_type=QuantType.QUInt8, weight_type=QuantType.QInt8)

    pairs = pd.read_parquet(Path(a.data) / "pairs_test.parquet")
    ca, cb, same = [], [], []
    for _, r in pairs.iterrows():
        x, y = crop_of(eng, r.img_0["bytes"]), crop_of(eng, r.img_1["bytes"])
        if x is not None and y is not None:
            ca.append(x); cb.append(y); same.append(bool(r.pair))
    same = np.array(same)
    print(f"{len(same)} verification pairs usable ({int(same.sum())} same person, {int((~same).sum())} different)")

    if base != src:
        base.unlink()
    f32, i8 = sess(src), sess(a.out)
    e32a, e32b, e8a, e8b = embed_all(f32, ca), embed_all(f32, cb), embed_all(i8, ca), embed_all(i8, cb)
    print(f"same photo, FP32 vs INT8 embedding: mean cosine {(e32a * e8a).sum(1).mean():.4f}, worst {(e32a * e8a).sum(1).min():.3f}")
    r32, r8 = verification(e32a, e32b, same), verification(e8a, e8b, same)
    print(f"\n{'':8}{'size':>8}{'ms':>7}{'acc@45%':>9}{'best acc':>10}{'(thr)':>7}{'TAR@FAR0.1%':>13}{'same/diff mean':>16}")
    for label, s, r, path in (("FP32", f32, r32, src), ("INT8", i8, r8, Path(a.out))):
        x = blob(ca[0]); n = s.get_inputs()[0].name
        for _ in range(5): s.run(None, {n: x})
        t = []
        for _ in range(60):
            q = time.perf_counter(); s.run(None, {n: x}); t.append((time.perf_counter() - q) * 1000)
        print(f"{label:8}{path.stat().st_size / 1e6:>6.1f}MB{np.median(t):>7.1f}{r['acc_at_bin_threshold']:>9.1%}{r['best_acc']:>10.1%}{r['best_threshold']:>7.2f}"
              f"{r['tar_at_far_0.1%']:>13.1%}{r['mean_same']:>9.2f}/{r['mean_diff']:.2f}")


if __name__ == "__main__":
    main()
