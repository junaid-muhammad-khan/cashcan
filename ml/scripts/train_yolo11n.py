"""
EXPERIMENT variant: YOLO11n-cls (Ultralytics' nano classification model) instead of
MobileNetV2, to see if a newer architecture closes any more of the train/val -> RealWaste
test generalization gap. Uses the SAME data/processed/{train,val,test} folders as train.py
(Ultralytics classification expects exactly this train/<class>/*.jpg layout already).

Run from ml/: python scripts/train_yolo11n.py
Outputs are written under separate "yolo11n_*" filenames so they don't clobber the
MobileNetV2 run in models/.
"""
import json
from pathlib import Path

import numpy as np
import torch
import yaml
from PIL import Image
from sklearn.metrics import classification_report, confusion_matrix
from ultralytics import YOLO

SEED = 42
EPOCHS = 12
IMG_SIZE = 224
BATCH_SIZE = 32

ML_ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ML_ROOT / "data" / "processed"
MODELS_DIR = ML_ROOT / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)


def get_device():
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return 0
    return "cpu"


def evaluate_test(model, classes):
    all_preds, all_labels = [], []
    for class_idx, cls in enumerate(classes):
        for img_path in sorted((PROCESSED / "test" / cls).iterdir()):
            img = Image.open(img_path).convert("RGB")
            result = model.predict(img, imgsz=IMG_SIZE, verbose=False)[0]
            pred_idx = result.probs.top1
            pred_name = model.names[pred_idx]
            all_preds.append(classes.index(pred_name))
            all_labels.append(class_idx)
    return all_labels, all_preds


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
    ax.set_title("YOLO11n-cls - confusion matrix - RealWaste test set (held out)")
    for i in range(len(classes)):
        for j in range(len(classes)):
            ax.text(j, i, str(cm[i, j]), ha="center", va="center",
                     color="white" if cm[i, j] > cm.max() / 2 else "black")
    fig.colorbar(im)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def main():
    device = get_device()
    print(f"Using device: {device}")

    class_map = yaml.safe_load((ML_ROOT / "class_map.yaml").read_text())
    classes = sorted(class_map["unified_classes"])
    print(f"Classes: {classes}")

    model = YOLO("yolo11n-cls.pt")
    model.train(
        data=str(PROCESSED),
        epochs=EPOCHS,
        imgsz=IMG_SIZE,
        batch=BATCH_SIZE,
        device=device,
        seed=SEED,
        project=str(MODELS_DIR / "yolo11n_runs"),
        name="train",
        exist_ok=True,
        verbose=True,
    )

    # Reload the best checkpoint for evaluation
    best_pt = MODELS_DIR / "yolo11n_runs" / "train" / "weights" / "best.pt"
    model = YOLO(str(best_pt))

    print("\n=== Evaluating on RealWaste test set (held out, never trained on) ===")
    all_labels, all_preds = evaluate_test(model, classes)
    report = classification_report(all_labels, all_preds, target_names=classes, output_dict=True, zero_division=0)
    cm = confusion_matrix(all_labels, all_preds)
    print(json.dumps(report, indent=2))

    save_confusion_matrix(cm, classes, MODELS_DIR / "yolo11n_confusion_matrix.png")

    metrics_out = {
        "model": "yolo11n-cls",
        "classes": classes,
        "test_classification_report": report,
        "test_confusion_matrix": cm.tolist(),
        "seed": SEED,
        "device": str(device),
    }
    (MODELS_DIR / "yolo11n_metrics.json").write_text(json.dumps(metrics_out, indent=2))

    # Export ONNX for comparison / potential RKNN conversion
    model.export(format="onnx", imgsz=IMG_SIZE)
    onnx_src = best_pt.with_suffix(".onnx")
    onnx_dst = MODELS_DIR / "yolo11n_cashcan.onnx"
    if onnx_src.exists():
        onnx_src.rename(onnx_dst)
        print(f"Exported ONNX model to {onnx_dst}")

    print(f"\nSaved checkpoint, confusion matrix, and metrics to {MODELS_DIR}")


if __name__ == "__main__":
    main()
