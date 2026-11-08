"""Retrain the 3-bin classifier on labels that follow CashCan's rule, and measure it on photos it never trains on.

  Recycle ("cans" bin) = cans and bottles that can be recycled (drink cans, tins, aerosols, plastic and glass bottles, jars, jugs, cartons)
  Organics             = food scraps and plants
  Waste                = everything else (paper, cardboard, foil, wrappers, bags, trays, lids, foam, textiles, trash ...)

Labels come from the datasets' folders plus relabel/containers.csv (CLIP, spot-checked by eye) for the glass/metal/plastic photos, so a plastic
bag is Waste and a plastic bottle is Recycle. Photos CLIP was unsure about are left out. 70/15/15 train/val/test split, seeded; the test split is
never used for training or for picking the best epoch. Starts from the previous checkpoint (models/mobilenetv2_cashcan.pt) and fine-tunes.

  python scripts/train_containers.py --trashnet DIR --realwaste DIR [--epochs 5]
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from PIL import Image
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler
from torchvision import models, transforms

ML = Path(__file__).resolve().parent.parent
MODELS = ML / "models"
CLASSES = ["cans", "organics", "waste"]
IMG = 224
EXT = {".jpg", ".jpeg", ".png"}
RW = {"Cardboard": "waste", "Paper": "waste", "Miscellaneous Trash": "waste", "Textile Trash": "waste", "Food Organics": "organics", "Vegetation": "organics"}
TN = {"cardboard": "waste", "paper": "waste", "trash": "waste"}   # glass/metal/plastic come from the CLIP file


def build_manifest(trashnet: Path, realwaste: Path, csv_path: Path):
    rows = []   # (path, label, source)
    for sub, lab in TN.items():
        rows += [(p, lab, "trashnet") for p in sorted((trashnet / sub).iterdir()) if p.suffix.lower() in EXT]
    for sub, lab in RW.items():
        rows += [(p, lab, "realwaste") for p in sorted((realwaste / sub).iterdir()) if p.suffix.lower() in EXT]
    folder = {"glass": "Glass", "metal": "Metal", "plastic": "Plastic"}
    for r in csv.DictReader(open(csv_path)):
        if r["decision"] == "unsure":
            continue
        root = trashnet / r["material"] if r["dataset"] == "trashnet" else realwaste / folder[r["material"]]
        rows.append((root / r["file"], "cans" if r["decision"] == "container" else "waste", r["dataset"]))
    return rows


def split(rows, seed=42):
    rng = random.Random(seed)
    by = defaultdict(list)
    for r in rows:
        by[r[1]].append(r)
    out = {"train": [], "val": [], "test": []}
    for lab, items in by.items():
        rng.shuffle(items)
        n = len(items); a, b = int(n * 0.70), int(n * 0.85)
        out["train"] += items[:a]; out["val"] += items[a:b]; out["test"] += items[b:]
    return out


class DS(Dataset):
    def __init__(self, rows, tf):
        self.rows, self.tf = rows, tf

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        p, lab, _ = self.rows[i]
        return self.tf(Image.open(p).convert("RGB")), CLASSES.index(lab)


def model_from(ckpt):
    m = models.mobilenet_v2(weights=None)
    m.classifier[1] = nn.Linear(m.last_channel, len(CLASSES))
    if ckpt:
        m.load_state_dict(torch.load(ckpt, map_location="cpu"))
    return m


@torch.no_grad()
def predict(m, loader):
    m.eval(); ys, ps = [], []
    for x, y in loader:
        ps += m(x).argmax(1).tolist(); ys += y.tolist()
    return np.array(ys), np.array(ps)


def report(name, y, p):
    acc = (y == p).mean() * 100
    per = {c: (p[y == i] == i).mean() * 100 for i, c in enumerate(CLASSES)}
    print(f"{name:14} accuracy {acc:5.1f}%   " + "  ".join(f"{c} {v:5.1f}%" for c, v in per.items()))
    return {"accuracy": round(acc, 2), "per_class_recall": {c: round(v, 2) for c, v in per.items()}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trashnet", required=True); ap.add_argument("--realwaste", required=True)
    ap.add_argument("--csv", default=str(ML / "relabel" / "containers.csv"))
    ap.add_argument("--epochs", type=int, default=5); ap.add_argument("--limit", type=int, default=0, help="smoke test: use only N training photos")
    ap.add_argument("--out", default=str(MODELS / "mobilenetv2_cashcan_v2"))
    a = ap.parse_args()
    torch.manual_seed(0); random.seed(0); np.random.seed(0)
    torch.set_num_threads(4)

    rows = build_manifest(Path(a.trashnet), Path(a.realwaste), Path(a.csv))
    sp = split(rows)
    print({k: dict(Counter(r[1] for r in v)) for k, v in sp.items()}, flush=True)
    (ML / "relabel").mkdir(exist_ok=True)
    with open(ML / "relabel" / "split.csv", "w", newline="") as fh:   # which photo was in which split (test photos were never trained on)
        w = csv.writer(fh); w.writerow(["split", "source", "label", "file"])
        for k, v in sp.items():
            for p, lab, src in v:
                w.writerow([k, src, lab, p.name])

    norm = transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    train_tf = transforms.Compose([transforms.RandomResizedCrop(IMG, scale=(0.5, 1.0)), transforms.RandomHorizontalFlip(), transforms.RandomRotation(25),
                                   transforms.ColorJitter(0.35, 0.35, 0.35), transforms.ToTensor(), norm])
    eval_tf = transforms.Compose([transforms.Resize((IMG, IMG), interpolation=transforms.InterpolationMode.BILINEAR), transforms.ToTensor(), norm])
    train_rows = sp["train"][: a.limit] if a.limit else sp["train"]
    counts = Counter(r[1] for r in train_rows)
    sampler = WeightedRandomSampler([1.0 / counts[r[1]] for r in train_rows], num_samples=len(train_rows), replacement=True)
    tl = DataLoader(DS(train_rows, train_tf), batch_size=32, sampler=sampler, num_workers=4)
    vl = DataLoader(DS(sp["val"], eval_tf), batch_size=64, num_workers=4)
    te = DataLoader(DS(sp["test"], eval_tf), batch_size=64, num_workers=4)

    old = model_from(MODELS / "mobilenetv2_cashcan.pt")
    yt, pt = predict(old, te)
    print("\nHELD-OUT TEST (%d photos never trained on), labels by CashCan's rule:" % len(yt))
    res = {"old_model": report("previous model", yt, pt)}

    m = model_from(MODELS / "mobilenetv2_cashcan.pt")
    opt = torch.optim.AdamW([{"params": m.features.parameters(), "lr": 1e-4}, {"params": m.classifier.parameters(), "lr": 1e-3}], weight_decay=1e-4)
    steps = a.epochs * len(tl)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=[2e-4, 2e-3], total_steps=steps, pct_start=0.2)
    crit = nn.CrossEntropyLoss(label_smoothing=0.05)
    best, best_state = -1.0, None
    t0 = time.time()
    for ep in range(1, a.epochs + 1):
        m.train(); tot = 0.0
        for i, (x, y) in enumerate(tl):
            opt.zero_grad(); loss = crit(m(x), y); loss.backward(); opt.step(); sched.step(); tot += loss.item()
            if i % 40 == 0:
                print(f"  epoch {ep} batch {i}/{len(tl)} loss {loss.item():.3f}  ({time.time() - t0:.0f}s)", flush=True)
        yv, pv = predict(m, vl)
        va = (yv == pv).mean() * 100
        print(f"epoch {ep}/{a.epochs}  train_loss {tot / len(tl):.3f}  val_acc {va:.1f}%  ({time.time() - t0:.0f}s)", flush=True)
        if va > best:
            best, best_state = va, {k: v.clone() for k, v in m.state_dict().items()}
    m.load_state_dict(best_state)
    yt, pt = predict(m, te)
    print("\nHELD-OUT TEST, retrained model:")
    res["new_model"] = report("retrained", yt, pt)
    from sklearn.metrics import confusion_matrix
    res["confusion_matrix_new[true x pred: cans, organics, waste]"] = confusion_matrix(yt, pt).tolist()
    print("confusion (rows = true, cols = predicted; cans, organics, waste):\n", np.array(res["confusion_matrix_new[true x pred: cans, organics, waste]"]))
    res["test_photos"] = len(yt); res["train_photos"] = len(train_rows); res["epochs"] = a.epochs
    torch.save(best_state, a.out + ".pt")
    m.eval()
    torch.onnx.export(m.cpu(), torch.randn(1, 3, IMG, IMG), a.out + ".onnx", input_names=["input"], output_names=["output"],
                      dynamic_axes={"input": {0: "batch"}, "output": {0: "batch"}}, opset_version=13)
    (Path(a.out).with_suffix(".json")).write_text(json.dumps(res, indent=2))
    print("saved", a.out + ".pt/.onnx")


if __name__ == "__main__":
    main()
