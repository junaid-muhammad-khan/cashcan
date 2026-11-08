"""
Train a MobileNetV2-1.0 classifier (transfer learning) on data/processed/train+val,
then evaluate honestly on data/processed/test (RealWaste - a dataset the model never
sees during training). Saves the best checkpoint, an ONNX export, a confusion matrix
image, and a metrics report.

MobileNetV2 (not V3) was chosen to match the garbage-classifier spec for the RK3582 NPU
deployment target (224x224, INT8-quantizable, official Rockchip RKNN conversion example).
The ONNX export here is the documented handoff format for RKNN-Toolkit2 conversion, which
must run on a separate x86 Linux machine (see scripts/convert_rknn.py).

Run from ml/: python scripts/train.py
"""
import json
import random
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import yaml
from sklearn.metrics import classification_report, confusion_matrix
from torch.utils.data import DataLoader, WeightedRandomSampler
from torchvision import datasets, models, transforms

SEED = 42
BATCH_SIZE = 32
EPOCHS = 12
HEAD_LR = 1e-3
BACKBONE_LR = 1e-4  # smaller LR for pretrained layers we're now fine-tuning, not just the head
IMG_SIZE = 224

ML_ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ML_ROOT / "data" / "processed"
MODELS_DIR = ML_ROOT / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)


def set_seed(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def get_device():
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def build_dataloaders(classes):
    # ImageNet normalization stats, since MobileNetV3 was pretrained on ImageNet.
    normalize = transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])

    train_tf = transforms.Compose([
        # RandomResizedCrop (not a fixed Resize) so the model doesn't latch onto a single
        # background/framing convention - helps cross-dataset generalization (RealWaste was
        # shot very differently from GD/TrashNet).
        transforms.RandomResizedCrop(IMG_SIZE, scale=(0.6, 1.0)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomRotation(20),
        transforms.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.3),
        transforms.ToTensor(),
        normalize,
    ])
    eval_tf = transforms.Compose([
        transforms.Resize((IMG_SIZE, IMG_SIZE)),
        transforms.ToTensor(),
        normalize,
    ])

    train_ds = datasets.ImageFolder(PROCESSED / "train", transform=train_tf)
    val_ds = datasets.ImageFolder(PROCESSED / "val", transform=eval_tf)
    test_ds = datasets.ImageFolder(PROCESSED / "test", transform=eval_tf)

    # ImageFolder sorts classes alphabetically; confirm that matches class_map.yaml order
    # assumption so label indices are consistent across train/val/test.
    assert train_ds.classes == val_ds.classes == test_ds.classes, (
        f"Class order mismatch: train={train_ds.classes} val={val_ds.classes} test={test_ds.classes}"
    )
    print(f"Class order (label indices): {train_ds.classes}")

    # Oversample organics at the batch level (on top of the loss class-weighting) since it's
    # only ~4.7% of train data and otherwise barely gets seen per epoch.
    class_counts = np.bincount(train_ds.targets, minlength=len(train_ds.classes))
    sample_weights = [1.0 / class_counts[t] for t in train_ds.targets]
    sampler = WeightedRandomSampler(sample_weights, num_samples=len(sample_weights), replacement=True)

    # num_workers=0 serializes image decode/augmentation on the main thread, blocking the GPU
    # between every batch - on this 10-core Mac that made epoch 1 take 8+ minutes with nothing
    # printed yet. Parallelize across worker processes instead.
    NUM_WORKERS = 4
    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, sampler=sampler,
                               num_workers=NUM_WORKERS, persistent_workers=True)
    val_loader = DataLoader(val_ds, batch_size=BATCH_SIZE, shuffle=False,
                             num_workers=NUM_WORKERS, persistent_workers=True)
    test_loader = DataLoader(test_ds, batch_size=BATCH_SIZE, shuffle=False,
                              num_workers=NUM_WORKERS, persistent_workers=True)
    return train_loader, val_loader, test_loader, train_ds.classes


def build_model(num_classes, device):
    # MobileNetV2-1.0 (not V3): matches the deployment target's recommended garbage-classifier
    # spec (224x224, INT8-quantizable) and has an official Rockchip RKNN conversion example,
    # unlike V3's newer ops which are less consistently supported by NPU toolchains.
    model = models.mobilenet_v2(weights=models.MobileNet_V2_Weights.IMAGENET1K_V1)
    # Fine-tune the whole backbone (not just the classifier head) so the model can adapt its
    # features to our domain instead of being stuck with generic ImageNet features.
    in_features = model.classifier[-1].in_features
    model.classifier[-1] = nn.Linear(in_features, num_classes)
    return model.to(device)


def run_epoch(model, loader, criterion, optimizer, device, train):
    model.train() if train else model.eval()
    total_loss, correct, total = 0.0, 0, 0
    n_batches = len(loader)
    with torch.set_grad_enabled(train):
        for batch_idx, (images, labels) in enumerate(loader):
            images, labels = images.to(device), labels.to(device)
            if train:
                optimizer.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, labels)
            if train:
                loss.backward()
                optimizer.step()
            total_loss += loss.item() * images.size(0)
            correct += (outputs.argmax(1) == labels).sum().item()
            total += images.size(0)
            if train and (batch_idx + 1) % 50 == 0:
                print(f"  batch {batch_idx + 1}/{n_batches}  running_loss={total_loss / total:.4f}", flush=True)
    return total_loss / total, correct / total


def evaluate_test(model, test_loader, classes, device):
    model.eval()
    all_preds, all_labels = [], []
    with torch.no_grad():
        for images, labels in test_loader:
            images = images.to(device)
            outputs = model(images)
            preds = outputs.argmax(1).cpu().numpy()
            all_preds.extend(preds.tolist())
            all_labels.extend(labels.numpy().tolist())

    report = classification_report(all_labels, all_preds, target_names=classes, output_dict=True, zero_division=0)
    cm = confusion_matrix(all_labels, all_preds)
    return report, cm, all_labels, all_preds


def save_confusion_matrix(cm, classes, path):
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6, 5))
    im = ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(len(classes)))
    ax.set_yticks(range(len(classes)))
    ax.set_xticklabels(classes)
    ax.set_yticklabels(classes)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    ax.set_title("Confusion matrix - RealWaste test set (held out, never trained on)")
    for i in range(len(classes)):
        for j in range(len(classes)):
            ax.text(j, i, str(cm[i, j]), ha="center", va="center",
                     color="white" if cm[i, j] > cm.max() / 2 else "black")
    fig.colorbar(im)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def main():
    set_seed(SEED)
    device = get_device()
    print(f"Using device: {device}")

    class_map = yaml.safe_load((ML_ROOT / "class_map.yaml").read_text())
    unified_classes = sorted(class_map["unified_classes"])  # ImageFolder sorts alphabetically

    train_loader, val_loader, test_loader, classes = build_dataloaders(unified_classes)
    assert classes == unified_classes, f"{classes} != {unified_classes}"

    model = build_model(len(classes), device)
    # The WeightedRandomSampler (in build_dataloaders) already balances class frequency per
    # batch, so we don't also apply loss class-weighting - stacking both tends to overcorrect
    # and tank precision on the majority classes.
    criterion = nn.CrossEntropyLoss()
    # Differential learning rates: smaller for the pretrained backbone (fine-tune gently),
    # larger for the freshly-initialized classifier head.
    optimizer = torch.optim.Adam([
        {"params": model.features.parameters(), "lr": BACKBONE_LR},
        {"params": model.classifier.parameters(), "lr": HEAD_LR},
    ])

    best_val_acc = 0.0
    best_state = None
    history = []
    for epoch in range(1, EPOCHS + 1):
        train_loss, train_acc = run_epoch(model, train_loader, criterion, optimizer, device, train=True)
        val_loss, val_acc = run_epoch(model, val_loader, criterion, optimizer, device, train=False)
        print(f"Epoch {epoch}/{EPOCHS}  train_loss={train_loss:.4f} train_acc={train_acc:.4f}  "
              f"val_loss={val_loss:.4f} val_acc={val_acc:.4f}")
        history.append({"epoch": epoch, "train_loss": train_loss, "train_acc": train_acc,
                         "val_loss": val_loss, "val_acc": val_acc})
        if val_acc > best_val_acc:
            best_val_acc = val_acc
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}

    model.load_state_dict(best_state)
    torch.save(model.state_dict(), MODELS_DIR / "mobilenetv2_cashcan.pt")
    print(f"\nBest val_acc: {best_val_acc:.4f} (checkpoint saved)")

    print("\n=== Evaluating on RealWaste test set (held out, never trained on) ===")
    report, cm, _, _ = evaluate_test(model, test_loader, classes, device)
    print(json.dumps(report, indent=2))

    save_confusion_matrix(cm, classes, MODELS_DIR / "confusion_matrix.png")

    metrics_out = {
        "classes": classes,
        "best_val_acc": best_val_acc,
        "train_history": history,
        "test_classification_report": report,
        "test_confusion_matrix": cm.tolist(),
        "seed": SEED,
        "device": str(device),
    }
    (MODELS_DIR / "metrics.json").write_text(json.dumps(metrics_out, indent=2))
    print(f"\nSaved checkpoint, confusion_matrix.png, and metrics.json to {MODELS_DIR}")

    # --- Export to ONNX for Raspberry Pi inference ---
    model.eval()
    dummy_input = torch.randn(1, 3, IMG_SIZE, IMG_SIZE, device=device)
    onnx_path = MODELS_DIR / "mobilenetv2_cashcan.onnx"
    torch.onnx.export(
        model.cpu(), dummy_input.cpu(), onnx_path,
        input_names=["input"], output_names=["output"],
        dynamic_axes={"input": {0: "batch"}, "output": {0: "batch"}},
        opset_version=13,
    )
    (MODELS_DIR / "classes.json").write_text(json.dumps(classes))
    print(f"Exported ONNX model to {onnx_path}")


if __name__ == "__main__":
    main()
