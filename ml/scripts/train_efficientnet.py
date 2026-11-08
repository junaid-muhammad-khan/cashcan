"""
EXPERIMENT variant of train.py: same pipeline, swapped to EfficientNetV2S (the backbone
the GD paper itself got its best same-domain results with: 95% F1), to see if a stronger
backbone narrows the train/val -> RealWaste test generalization gap that MobileNetV3-small
hit (63.6% test acc, 17% organics recall, despite 96.7% val acc).

Run from ml/: python scripts/train_efficientnet.py
Outputs are written under separate "efficientnetv2s_*" filenames so they don't clobber
the MobileNetV3 run in models/.
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
BATCH_SIZE = 16  # EfficientNetV2S is much heavier than MobileNetV3-small; smaller batch for memory
EPOCHS = 6        # fewer epochs to offset the heavier per-step cost, same ~1hr-ish budget spirit
HEAD_LR = 1e-3
BACKBONE_LR = 1e-4
IMG_SIZE = 256    # EfficientNetV2S's native recommended size is 384; 256 is a speed compromise

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
    normalize = transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])

    train_tf = transforms.Compose([
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

    assert train_ds.classes == val_ds.classes == test_ds.classes, (
        f"Class order mismatch: train={train_ds.classes} val={val_ds.classes} test={test_ds.classes}"
    )
    print(f"Class order (label indices): {train_ds.classes}")

    class_counts = np.bincount(train_ds.targets, minlength=len(train_ds.classes))
    sample_weights = [1.0 / class_counts[t] for t in train_ds.targets]
    sampler = WeightedRandomSampler(sample_weights, num_samples=len(sample_weights), replacement=True)

    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, sampler=sampler, num_workers=0)
    val_loader = DataLoader(val_ds, batch_size=BATCH_SIZE, shuffle=False, num_workers=0)
    test_loader = DataLoader(test_ds, batch_size=BATCH_SIZE, shuffle=False, num_workers=0)
    return train_loader, val_loader, test_loader, train_ds.classes


def build_model(num_classes, device):
    model = models.efficientnet_v2_s(weights=models.EfficientNet_V2_S_Weights.IMAGENET1K_V1)
    in_features = model.classifier[-1].in_features
    model.classifier[-1] = nn.Linear(in_features, num_classes)
    return model.to(device)


def run_epoch(model, loader, criterion, optimizer, device, train):
    model.train() if train else model.eval()
    total_loss, correct, total = 0.0, 0, 0
    with torch.set_grad_enabled(train):
        for images, labels in loader:
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
    ax.set_title("EfficientNetV2S - confusion matrix - RealWaste test set (held out)")
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
    unified_classes = sorted(class_map["unified_classes"])

    train_loader, val_loader, test_loader, classes = build_dataloaders(unified_classes)
    assert classes == unified_classes, f"{classes} != {unified_classes}"

    model = build_model(len(classes), device)
    criterion = nn.CrossEntropyLoss()
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
    torch.save(model.state_dict(), MODELS_DIR / "efficientnetv2s_cashcan.pt")
    print(f"\nBest val_acc: {best_val_acc:.4f} (checkpoint saved)")

    print("\n=== Evaluating on RealWaste test set (held out, never trained on) ===")
    report, cm, _, _ = evaluate_test(model, test_loader, classes, device)
    print(json.dumps(report, indent=2))

    save_confusion_matrix(cm, classes, MODELS_DIR / "efficientnetv2s_confusion_matrix.png")

    metrics_out = {
        "model": "efficientnet_v2_s",
        "classes": classes,
        "best_val_acc": best_val_acc,
        "train_history": history,
        "test_classification_report": report,
        "test_confusion_matrix": cm.tolist(),
        "seed": SEED,
        "device": str(device),
    }
    (MODELS_DIR / "efficientnetv2s_metrics.json").write_text(json.dumps(metrics_out, indent=2))
    print(f"\nSaved checkpoint, confusion matrix, and metrics to {MODELS_DIR}")


if __name__ == "__main__":
    main()
