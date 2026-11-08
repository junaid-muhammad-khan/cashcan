"""
Fine-tune the classifier on photos taken by the bin's own camera (the ones you teach with R/O/W:
~/.cashcan/taught_photos/<cans|organics|waste>/*.jpg), mixed with the public training set so it does not forget it.

- Photos are grouped into "holds" (frames less than 3 s apart = the same item held still). Whole holds go to the camera
  test set, never part of one: frames in a hold are near-copies, so a random split would grade the model on its own training photos.
- Camera photos are ~CAMERA_SHARE of every training batch (the public set would otherwise drown ~400 photos out).
- Writes SEPARATE files (mobilenetv2_cashcan_camera.*, metrics_camera.json). The model the bin uses is NOT touched.

Run from ml/:  .venv/bin/python scripts/train_camera.py [--epochs 6] [--photos DIR]
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import yaml
from PIL import Image
from torch.utils.data import ConcatDataset, DataLoader, Dataset, WeightedRandomSampler
from torchvision import datasets, transforms

sys.path.insert(0, str(Path(__file__).resolve().parent))
import train as base  # noqa: E402

IMG = base.IMG_SIZE
NORM = transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
TRAIN_TF = transforms.Compose([
    transforms.RandomResizedCrop(IMG, scale=(0.5, 1.0)), transforms.RandomRotation(20), transforms.RandomHorizontalFlip(),
    transforms.ColorJitter(brightness=0.35, contrast=0.35, saturation=0.35), transforms.ToTensor(), NORM])
EVAL_TF = transforms.Compose([transforms.Resize((IMG, IMG)), transforms.ToTensor(), NORM])
CAMERA_SHARE = 0.35


class Photos(Dataset):
    def __init__(self, items, transform):  # items: [(path, class_index)]
        self.items, self.transform = items, transform

    def __len__(self):
        return len(self.items)

    def __getitem__(self, i):
        p, y = self.items[i]
        with Image.open(p) as im:
            return self.transform(im.convert("RGB")), y


def holds_of(folder: Path) -> list[list[Path]]:
    files = sorted(folder.glob("*.jpg"))
    stamp = lambda f: dt.datetime.strptime(f.name.split("_")[0], "%Y%m%d-%H%M%S")
    out = []
    for f in files:
        if out and (stamp(f) - stamp(out[-1][-1])).total_seconds() <= 3:
            out[-1].append(f)
        else:
            out.append([f])
    return out


def split_holds(photos: Path, classes):
    train, test = [], []
    for ci, c in enumerate(classes):
        holds = holds_of(photos / c)
        # a class with one hold has nothing to test on: all of it trains. Otherwise the LAST hold is held out.
        for k, h in enumerate(holds):
            (test if len(holds) > 1 and k == len(holds) - 1 else train).extend((p, ci) for p in h)
    return train, test


def predict(model, loader, device):
    model.eval()
    ys, ps = [], []
    with torch.no_grad():
        for x, y in loader:
            ps += model(x.to(device)).argmax(1).cpu().tolist()
            ys += y.tolist()
    return np.array(ys), np.array(ps)


def summarize(ys, ps, classes):
    out = {"n": int(len(ys)), "accuracy": float((ys == ps).mean()) if len(ys) else None}
    for ci, c in enumerate(classes):
        m = ys == ci
        out[f"{c}_recall"] = float((ps[m] == ci).mean()) if m.any() else None
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=6)
    ap.add_argument("--photos", default=str(Path.home() / ".cashcan" / "taught_photos"))
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    base.set_seed(base.SEED)
    device = base.get_device()
    classes = sorted(yaml.safe_load((base.ML_ROOT / "class_map.yaml").read_text())["unified_classes"])
    photos = Path(args.photos)
    cam_train, cam_test = split_holds(photos, classes)
    print(f"Camera photos: {len(cam_train)} train, {len(cam_test)} held-out (whole holds). Using device: {device}")
    for ci, c in enumerate(classes):
        print(f"  {c}: train {sum(y == ci for _, y in cam_train)}, test {sum(y == ci for _, y in cam_test)}")

    pub_train = datasets.ImageFolder(base.PROCESSED / "train", transform=TRAIN_TF)
    pub_val = datasets.ImageFolder(base.PROCESSED / "val", transform=EVAL_TF)
    pub_test = datasets.ImageFolder(base.PROCESSED / "test", transform=EVAL_TF)
    assert pub_train.classes == classes
    train_ds = ConcatDataset([pub_train, Photos(cam_train, TRAIN_TF)])

    # class-balanced, with the camera photos making up CAMERA_SHARE of what the model sees
    n_pub = len(pub_train)
    pub_counts = np.bincount(pub_train.targets, minlength=len(classes))
    cam_counts = np.bincount([y for _, y in cam_train], minlength=len(classes))
    weights = [(1 - CAMERA_SHARE) / pub_counts[t] / len(classes) for t in pub_train.targets] + \
              [CAMERA_SHARE / max(1, cam_counts[y]) / len(classes) for _, y in cam_train]
    sampler = WeightedRandomSampler(weights, num_samples=n_pub, replacement=True)
    w = args.workers
    train_loader = DataLoader(train_ds, batch_size=base.BATCH_SIZE, sampler=sampler, num_workers=w, persistent_workers=w > 0)
    mk = lambda ds: DataLoader(ds, batch_size=base.BATCH_SIZE, shuffle=False, num_workers=w)
    val_loader, test_loader = mk(pub_val), mk(pub_test)
    cam_loader = mk(Photos(cam_test, EVAL_TF)) if cam_test else None

    old_pt = base.MODELS_DIR / "mobilenetv2_cashcan.pt"
    model = base.build_model(len(classes), device)
    model.load_state_dict(torch.load(old_pt, map_location=device))
    old = base.build_model(len(classes), device)
    old.load_state_dict(torch.load(old_pt, map_location=device))
    optimizer = torch.optim.Adam([{"params": model.features.parameters(), "lr": 3e-5},
                                  {"params": model.classifier.parameters(), "lr": 2e-4}])
    criterion = nn.CrossEntropyLoss()

    def cam_acc(m):
        if cam_loader is None:
            return 0.0
        ys, ps = predict(m, cam_loader, device)
        return float((ys == ps).mean())

    best, best_state, history = -1.0, None, []
    for epoch in range(1, args.epochs + 1):
        tr_loss, tr_acc = base.run_epoch(model, train_loader, criterion, optimizer, device, train=True)
        _, pub_acc = base.run_epoch(model, val_loader, criterion, optimizer, device, train=False)
        ca = cam_acc(model)
        print(f"Epoch {epoch}/{args.epochs}  train_acc={tr_acc:.4f}  public_val={pub_acc:.4f}  camera_test={ca:.4f}", flush=True)
        history.append({"epoch": epoch, "train_acc": tr_acc, "public_val": pub_acc, "camera_test": ca})
        score = (pub_acc + ca) / 2
        if score > best:
            best, best_state = score, {k: v.cpu().clone() for k, v in model.state_dict().items()}
    model.load_state_dict(best_state)
    torch.save(model.state_dict(), base.MODELS_DIR / "mobilenetv2_cashcan_camera.pt")

    print("\n=== Old vs new ===")
    res = {"old": {}, "new": {}}
    for name, m in (("old", old), ("new", model)):
        ys, ps = predict(m, test_loader, device)
        res[name]["public_test"] = summarize(ys, ps, classes)
        if cam_loader is not None:
            ys, ps = predict(m, cam_loader, device)
            res[name]["camera_test"] = summarize(ys, ps, classes)
            res[name]["camera_test"]["waste_called_cans"] = int(((ys == classes.index("waste")) & (ps == classes.index("cans"))).sum())
    for k in res["old"]:
        o, n = res["old"][k], res["new"][k]
        print(f"{k}: accuracy {o['accuracy']:.3f} -> {n['accuracy']:.3f}   " +
              "  ".join(f"{c} recall {o[f'{c}_recall']:.2f} -> {n[f'{c}_recall']:.2f}" for c in classes if o[f"{c}_recall"] is not None))
    (base.MODELS_DIR / "metrics_camera.json").write_text(json.dumps(
        {"classes": classes, "history": history, "results": res, "camera_train": len(cam_train), "camera_test": len(cam_test),
         "note": "Camera test = whole held-out holds from ONE session in one room: a small, easy test. Treat it as a smoke check."}, indent=2))

    model.eval()
    torch.onnx.export(model.cpu(), torch.randn(1, 3, IMG, IMG), base.MODELS_DIR / "mobilenetv2_cashcan_camera.onnx",
                      input_names=["input"], output_names=["output"], dynamic_axes={"input": {0: "batch"}, "output": {0: "batch"}}, opset_version=13)
    print(f"\nSaved mobilenetv2_cashcan_camera.pt/.onnx and metrics_camera.json to {base.MODELS_DIR}. The live model is unchanged.")


if __name__ == "__main__":
    main()
