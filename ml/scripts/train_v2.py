"""
Retrain the 3-bin classifier so it also recognises items that are FAR from the camera.

What changes vs train.py:
  - ~65% of training images go through DistanceAug (scripts/distance_aug.py): the item is shrunk to 12-70% of the
    frame, placed on another background and softened. The rest keep the normal close-up augmentation.
  - Starts from the current model (keeps what it learned from the webcam photos), then fine-tunes. --from-scratch
    starts from ImageNet instead.
  - The best epoch is chosen on close-up AND far validation accuracy, so it cannot get better at one by getting
    worse at the other.
  - Writes SEPARATE files (mobilenetv2_cashcan_v2.*, metrics_v2.json). The model the bin uses is NOT touched.
  - At the end it scores the old and the new model on the held-out test set at several distances.

Run from ml/:  .venv/bin/python scripts/train_v2.py            (add --epochs 1 --subset 600 for a quick smoke test)
"""
import argparse
import json
import random
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import yaml
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler
from torchvision import datasets, transforms

sys.path.insert(0, str(Path(__file__).resolve().parent))
import train as base  # noqa: E402  (reuse the model, epoch loop, evaluation and paths)
from distance_aug import DistanceAug, list_images  # noqa: E402

IMG = base.IMG_SIZE
NORM = transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
TO_TENSOR = transforms.Compose([transforms.ToTensor(), NORM])
EVAL_TF = transforms.Compose([transforms.Resize((IMG, IMG)), TO_TENSOR])
BENCH_SCALES = [None, 0.5, 0.3, 0.2, 0.12]  # None = the normal close-up; the rest = how much of the frame the item fills


class MixedTrainTransform:
    """With probability p_far: the item looks far away. Otherwise the usual close-up augmentation."""

    def __init__(self, distance: DistanceAug, p_far: float):
        self.distance, self.p_far = distance, p_far
        self.close = transforms.Compose([transforms.RandomResizedCrop(IMG, scale=(0.6, 1.0)), transforms.RandomRotation(20)])
        self.common = transforms.Compose([
            transforms.RandomHorizontalFlip(),
            transforms.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.3),
            TO_TENSOR,
        ])

    def __call__(self, img):
        img = self.distance(img) if random.random() < self.p_far else self.close(img)
        return self.common(img)


class FarDataset(Dataset):
    """The same images every time (seeded): every image shown with the item filling `scale` of the frame."""

    def __init__(self, base_ds, scale, distance, seed=0):
        self.base_ds, self.scale, self.distance, self.seed = base_ds, scale, distance, seed

    def __len__(self):
        return len(self.base_ds)

    def __getitem__(self, i):
        img, label = self.base_ds[i]
        if self.scale is None:
            return EVAL_TF(img), label
        rng = random.Random(self.seed * 1_000_003 + i)
        return TO_TENSOR(self.distance.apply(img.convert("RGB"), rng, scale=self.scale, degrade_p=0.7)), label


def make_loader(ds, workers):
    return DataLoader(ds, batch_size=base.BATCH_SIZE, shuffle=False, num_workers=workers, persistent_workers=workers > 0)


def score(model, loader, classes, device):
    report, cm, labels, preds = base.evaluate_test(model, loader, classes, device)
    labels, preds = np.array(labels), np.array(preds)
    ci, wi = classes.index("cans"), classes.index("waste")
    return {
        "accuracy": report["accuracy"],
        "cans_recall": report["cans"]["recall"],
        "cans_precision": report["cans"]["precision"],
        "waste_called_cans": int(((labels == wi) & (preds == ci)).sum()),
        "cans_called_waste": int(((labels == ci) & (preds == wi)).sum()),
    }


def far_accuracy(model, loader, device):
    model.eval()
    ok = n = 0
    with torch.no_grad():
        for x, y in loader:
            ok += (model(x.to(device)).argmax(1).cpu() == y).sum().item()
            n += len(y)
    return ok / n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=8)
    ap.add_argument("--p-far", type=float, default=0.65, help="share of training images shown as far away")
    ap.add_argument("--from-scratch", action="store_true", help="start from ImageNet instead of the current model")
    ap.add_argument("--subset", type=int, default=0, help="train on only N random images (smoke test)")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    base.set_seed(base.SEED)
    device = base.get_device()
    print(f"Using device: {device}")
    classes = sorted(yaml.safe_load((base.ML_ROOT / "class_map.yaml").read_text())["unified_classes"])

    train_ds = datasets.ImageFolder(base.PROCESSED / "train")  # transform set below, once the background pool exists
    val_raw = datasets.ImageFolder(base.PROCESSED / "val")
    test_raw = datasets.ImageFolder(base.PROCESSED / "test")
    assert train_ds.classes == val_raw.classes == test_raw.classes == classes

    if args.subset:
        keep = random.Random(1).sample(range(len(train_ds.samples)), min(args.subset, len(train_ds.samples)))
        train_ds.samples = [train_ds.samples[i] for i in keep]
        train_ds.targets = [train_ds.targets[i] for i in keep]

    real_bgs = list_images(base.ML_ROOT / "data" / "raw" / "backgrounds")
    print(f"Backgrounds: {len(train_ds.samples)} blurred training photos + gradients"
          + (f" + {len(real_bgs)} real bin-camera backgrounds" if real_bgs else " (no data/raw/backgrounds/ yet)"))
    distance = DistanceAug(IMG, bg_paths=[p for p, _ in train_ds.samples], real_bg_paths=real_bgs)
    train_ds.transform = MixedTrainTransform(distance, args.p_far)

    counts = np.bincount(train_ds.targets, minlength=len(classes))
    sampler = WeightedRandomSampler([1.0 / counts[t] for t in train_ds.targets], num_samples=len(train_ds), replacement=True)
    w = args.workers
    train_loader = DataLoader(train_ds, batch_size=base.BATCH_SIZE, sampler=sampler, num_workers=w, persistent_workers=w > 0)
    val_close = make_loader(FarDataset(val_raw, None, distance), w)
    val_far_distance = DistanceAug(IMG, bg_paths=[p for p, _ in val_raw.samples])  # backgrounds from val photos, not train
    val_far = make_loader(FarDataset(val_raw, 0.25, val_far_distance, seed=11), w)

    old_pt = base.MODELS_DIR / "mobilenetv2_cashcan.pt"
    model = base.build_model(len(classes), device)
    warm = old_pt.exists() and not args.from_scratch
    if warm:
        model.load_state_dict(torch.load(old_pt, map_location=device))
        print(f"Warm start from {old_pt.name}")
    backbone_lr, head_lr = (5e-5, 3e-4) if warm else (base.BACKBONE_LR, base.HEAD_LR)
    optimizer = torch.optim.Adam([{"params": model.features.parameters(), "lr": backbone_lr},
                                  {"params": model.classifier.parameters(), "lr": head_lr}])
    criterion = nn.CrossEntropyLoss()

    best_score, best_state, history = -1.0, None, []
    for epoch in range(1, args.epochs + 1):
        tr_loss, tr_acc = base.run_epoch(model, train_loader, criterion, optimizer, device, train=True)
        _, close_acc = base.run_epoch(model, val_close, criterion, optimizer, device, train=False)
        far_acc = far_accuracy(model, val_far, device)
        combined = (close_acc + far_acc) / 2
        print(f"Epoch {epoch}/{args.epochs}  train_acc={tr_acc:.4f}  val_close={close_acc:.4f}  val_far={far_acc:.4f}", flush=True)
        history.append({"epoch": epoch, "train_loss": tr_loss, "train_acc": tr_acc, "val_close": close_acc, "val_far": far_acc})
        if combined > best_score:
            best_score, best_state = combined, {k: v.cpu().clone() for k, v in model.state_dict().items()}
    model.load_state_dict(best_state)
    torch.save(model.state_dict(), base.MODELS_DIR / "mobilenetv2_cashcan_v2.pt")

    # ---- the comparison that matters: old vs new, on the held-out test set, at several distances ----
    print("\n=== Held-out test (40% of RealWaste), item filling a given share of the frame ===")
    bench_distance = DistanceAug(IMG, bg_paths=[p for p, _ in test_raw.samples])  # backgrounds from test photos only
    old = base.build_model(len(classes), device)
    old.load_state_dict(torch.load(old_pt, map_location=device)) if old_pt.exists() else None
    results = {"old": {}, "new": {}}
    for s in BENCH_SCALES:
        loader = make_loader(FarDataset(test_raw, s, bench_distance, seed=5), w)
        label = "close-up" if s is None else f"{int(s * 100)}%"
        for name, m in (("old", old), ("new", model)):
            results[name][label] = score(m, loader, classes, device)
        o, n = results["old"][label], results["new"][label]
        print(f"{label:>9}:  accuracy {o['accuracy']:.3f} -> {n['accuracy']:.3f}   cans recall {o['cans_recall']:.3f} -> "
              f"{n['cans_recall']:.3f}   waste called cans {o['waste_called_cans']} -> {n['waste_called_cans']}", flush=True)

    (base.MODELS_DIR / "metrics_v2.json").write_text(json.dumps(
        {"classes": classes, "p_far": args.p_far, "warm_start": warm, "epochs": args.epochs, "history": history,
         "distance_benchmark": results, "note": "Synthetic distance test: same family as the training augmentation, so it "
         "flatters the new model. The real check is photos from the bin camera at distance."}, indent=2))

    model.eval()
    onnx_path = base.MODELS_DIR / "mobilenetv2_cashcan_v2.onnx"
    torch.onnx.export(model.cpu(), torch.randn(1, 3, IMG, IMG), onnx_path, input_names=["input"], output_names=["output"],
                      dynamic_axes={"input": {0: "batch"}, "output": {0: "batch"}}, opset_version=13)
    print(f"\nSaved mobilenetv2_cashcan_v2.pt/.onnx and metrics_v2.json to {base.MODELS_DIR}. The live model is unchanged.")


if __name__ == "__main__":
    main()
