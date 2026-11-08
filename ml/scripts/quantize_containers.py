"""INT8-quantize the retrained container classifier and measure it on the held-out test split written by train_containers.py.

  python scripts/quantize_containers.py --trashnet DIR --realwaste DIR
"""
from __future__ import annotations

import argparse
import csv
import random
import sys
from pathlib import Path

import numpy as np
from onnxruntime.quantization import QuantFormat, QuantType, quantize_static

sys.path.insert(0, str(Path(__file__).resolve().parent))
from quantize_int8 import Reader, latency, prep, session   # noqa: E402

ML = Path(__file__).resolve().parent.parent
CLASSES = ["cans", "organics", "waste"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trashnet", required=True); ap.add_argument("--realwaste", required=True)
    ap.add_argument("--model", default=str(ML / "models" / "mobilenetv2_cashcan_v2.onnx"))
    ap.add_argument("--out", default=str(ML / "models" / "mobilenetv2_cashcan_v2_int8.onnx"))
    ap.add_argument("--n-calib", type=int, default=400)
    a = ap.parse_args()
    random.seed(0)
    index = {p.name: p for root in (a.trashnet, a.realwaste) for p in Path(root).rglob("*") if p.suffix.lower() in {".jpg", ".jpeg", ".png"}}
    rows = list(csv.DictReader(open(ML / "relabel" / "split.csv")))
    train = [index[r["file"]] for r in rows if r["split"] == "train"]
    test = [(index[r["file"]], r["label"]) for r in rows if r["split"] == "test"]
    random.shuffle(train)
    name = session(a.model).get_inputs()[0].name
    print(f"calibrating on {a.n_calib} training photos; evaluating on {len(test)} held-out photos ...")
    quantize_static(a.model, a.out, Reader(train[: a.n_calib], name), quant_format=QuantFormat.QDQ, per_channel=True,
                    activation_type=QuantType.QUInt8, weight_type=QuantType.QInt8)
    f32, i8 = session(a.model), session(a.out)
    res = []
    for p, lab in test:
        x = prep(p)
        res.append((lab, CLASSES[int(np.argmax(f32.run(None, {name: x})[0][0]))], CLASSES[int(np.argmax(i8.run(None, {name: x})[0][0]))]))
    n = len(res)
    acc = lambda k: 100 * sum(r[0] == r[k] for r in res) / n
    print(f"\n{'':8}{'size':>8}{'latency':>10}{'accuracy':>10}")
    print(f"{'FP32':8}{Path(a.model).stat().st_size / 1e6:>6.1f}MB{latency(f32, name):>7.1f} ms{acc(1):>9.1f}%")
    print(f"{'INT8':8}{Path(a.out).stat().st_size / 1e6:>6.1f}MB{latency(i8, name):>7.1f} ms{acc(2):>9.1f}%")
    print(f"same bin on {100 * sum(r[1] == r[2] for r in res) / n:.1f}% of the photos")
    for c in CLASSES:
        sel = [r for r in res if r[0] == c]
        print(f"  {c:9} FP32 {100 * sum(r[1] == c for r in sel) / len(sel):5.1f}%   INT8 {100 * sum(r[2] == c for r in sel) / len(sel):5.1f}%   ({len(sel)} photos)")
    waste = [r for r in res if r[0] == "waste"]
    print(f"waste items sent to the Recycle bin: FP32 {sum(r[1] == 'cans' for r in waste)}/{len(waste)}, INT8 {sum(r[2] == 'cans' for r in waste)}/{len(waste)}")


if __name__ == "__main__":
    main()
