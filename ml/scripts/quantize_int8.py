"""INT8-quantize the CashCan classifier for the Pi and measure what it costs.

  python scripts/quantize_int8.py --calib DIR [DIR ...] --eval DIR_WITH_CLASS_SUBFOLDERS [--map class_map.yaml dataset-name]

Static quantization (QDQ, per-channel weights) calibrated on real photos; no labels are needed for calibration. Prints, for FP32 vs INT8:
file size, latency, accuracy on the evaluation folders and how often the two models agree. Evaluation folders are named by material
(glass/metal/...) and mapped to the three bins with class_map.yaml, the same way training did.
Accuracy here is only a COMPARISON of the two models on the same images; if the images were part of training it is not a held-out score.
"""
from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort
import yaml
from onnxruntime.quantization import CalibrationDataReader, QuantFormat, QuantType, quantize_static
from PIL import Image

ML = Path(__file__).resolve().parent.parent
MODELS = ML / "models"
MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)
EXT = {".jpg", ".jpeg", ".png"}


def prep(path) -> np.ndarray:
    img = Image.open(path).convert("RGB").resize((224, 224), Image.BILINEAR)   # same as train.py / predict.py
    return (((np.asarray(img, np.float32) / 255.0) - MEAN) / STD).transpose(2, 0, 1)[None].astype(np.float32)


def images(folder: Path):
    return sorted(p for p in folder.rglob("*") if p.suffix.lower() in EXT)


class Reader(CalibrationDataReader):
    def __init__(self, paths, name):
        self._it = iter([{name: prep(p)} for p in paths])

    def get_next(self):
        return next(self._it, None)


def session(path, threads=None):
    o = ort.SessionOptions()
    o.log_severity_level = 3
    if threads:
        o.intra_op_num_threads = threads
    return ort.InferenceSession(str(path), o, providers=["CPUExecutionProvider"])


def latency(sess, name, n=60):
    x = prep(images(ML / "models")[0]) if False else np.random.default_rng(0).normal(size=(1, 3, 224, 224)).astype(np.float32)
    for _ in range(5):
        sess.run(None, {name: x})
    t = []
    for _ in range(n):
        s = time.perf_counter(); sess.run(None, {name: x}); t.append((time.perf_counter() - s) * 1000)
    return float(np.median(t))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--calib", required=True, nargs="+", help="folders of photos for calibration (any labels; mix datasets, include damaged/real-world items)")
    ap.add_argument("--n-calib", type=int, default=200)
    ap.add_argument("--eval", nargs="+", required=True, help="dataset folders with material subfolders, as NAME=PATH (NAME is a datasets key in class_map.yaml)")
    ap.add_argument("--per-class", type=int, default=150, help="max evaluation images per material folder")
    ap.add_argument("--model", default=str(MODELS / "mobilenetv2_cashcan.onnx"))
    ap.add_argument("--out", default=str(MODELS / "mobilenetv2_cashcan_int8.onnx"))
    a = ap.parse_args()
    random.seed(0)

    src = Path(a.model)
    name = session(src).get_inputs()[0].name
    calib = [p for d in a.calib for p in images(Path(d))]; random.shuffle(calib); calib = calib[: a.n_calib]
    print(f"calibrating on {len(calib)} photos ...")
    quantize_static(str(src), a.out, Reader(calib, name), quant_format=QuantFormat.QDQ, per_channel=True,
                    activation_type=QuantType.QUInt8, weight_type=QuantType.QInt8)

    classes = json.loads((MODELS / "classes.json").read_text())
    cmap = yaml.safe_load((ML / "class_map.yaml").read_text())["datasets"]
    f32, i8 = session(src), session(a.out)
    rows = []   # (true bin, fp32 pred, int8 pred)
    for spec in a.eval:
        ds, path = spec.split("=", 1)
        mapping = {k.lower(): v for k, v in cmap[ds]["mapping"].items()}
        for sub in sorted(p for p in Path(path).iterdir() if p.is_dir()):
            truth = mapping.get(sub.name.lower())
            if truth is None:
                continue
            files = images(sub); random.shuffle(files)
            for f in files[: a.per_class]:
                x = prep(f)
                rows.append((truth, classes[int(np.argmax(f32.run(None, {name: x})[0][0]))], classes[int(np.argmax(i8.run(None, {name: x})[0][0]))]))
    n = len(rows)
    acc = lambda k: 100 * sum(r[0] == r[k] for r in rows) / n
    agree = 100 * sum(r[1] == r[2] for r in rows) / n
    print(f"\n{n} evaluation photos")
    print(f"{'':10}{'size':>9}{'latency':>11}{'accuracy':>10}")
    print(f"{'FP32':10}{src.stat().st_size / 1e6:>7.1f}MB{latency(f32, name):>8.1f} ms{acc(1):>9.1f}%")
    print(f"{'INT8':10}{Path(a.out).stat().st_size / 1e6:>7.1f}MB{latency(i8, name):>8.1f} ms{acc(2):>9.1f}%")
    print(f"the two models give the same bin on {agree:.1f}% of the photos")
    for b in classes:
        sel = [r for r in rows if r[0] == b]
        if sel:
            print(f"  {b:9} FP32 {100 * sum(r[1] == b for r in sel) / len(sel):5.1f}%   INT8 {100 * sum(r[2] == b for r in sel) / len(sel):5.1f}%   ({len(sel)} photos)")


if __name__ == "__main__":
    main()
