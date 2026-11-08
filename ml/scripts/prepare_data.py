"""
Build train/val/test image folders from the raw datasets using class_map.yaml.

- train_val datasets (trashnet, gd) are split 80/20 into processed/train and processed/val.
- test_only datasets (realwaste) go entirely into processed/test. Never trained on.

Run from ml/: python scripts/prepare_data.py
"""
import random
import shutil
from pathlib import Path

import yaml

SEED = 42
VAL_FRACTION = 0.2
IMG_EXTS = {".jpg", ".jpeg", ".png"}

ML_ROOT = Path(__file__).resolve().parent.parent
RAW = ML_ROOT / "data" / "raw"
PROCESSED = ML_ROOT / "data" / "processed"


def list_images(folder: Path):
    return sorted(p for p in folder.iterdir() if p.suffix.lower() in IMG_EXTS and p.is_file())


def main():
    random.seed(SEED)
    class_map = yaml.safe_load((ML_ROOT / "class_map.yaml").read_text())
    unified_classes = class_map["unified_classes"]

    for split in ("train", "val", "test"):
        for cls in unified_classes:
            (PROCESSED / split / cls).mkdir(parents=True, exist_ok=True)

    counts = {"train": {c: 0 for c in unified_classes}, "val": {c: 0 for c in unified_classes}, "test": {c: 0 for c in unified_classes}}

    for ds_name, ds_cfg in class_map["datasets"].items():
        role = ds_cfg["role"]
        ds_path = ML_ROOT / ds_cfg["path"]
        mapping = ds_cfg["mapping"]

        for raw_class, unified_class in mapping.items():
            src_dir = ds_path / raw_class
            if not src_dir.is_dir():
                print(f"WARNING: {ds_name}/{raw_class} not found at {src_dir}, skipping")
                continue
            images = list_images(src_dir)
            if not images:
                print(f"WARNING: {ds_name}/{raw_class} has no images, skipping")
                continue

            if role == "train_val":
                random.shuffle(images)
                n_val = max(1, int(len(images) * VAL_FRACTION))
                val_imgs, train_imgs = images[:n_val], images[n_val:]
                for img in train_imgs:
                    dst = PROCESSED / "train" / unified_class / f"{ds_name}_{img.name}"
                    shutil.copy2(img, dst)
                    counts["train"][unified_class] += 1
                for img in val_imgs:
                    dst = PROCESSED / "val" / unified_class / f"{ds_name}_{img.name}"
                    shutil.copy2(img, dst)
                    counts["val"][unified_class] += 1
            elif role == "test_only":
                for img in images:
                    dst = PROCESSED / "test" / unified_class / f"{ds_name}_{img.name}"
                    shutil.copy2(img, dst)
                    counts["test"][unified_class] += 1
            else:
                raise ValueError(f"Unknown role {role!r} for dataset {ds_name!r}")

    print("\n=== Final processed counts ===")
    for split in ("train", "val", "test"):
        total = sum(counts[split].values())
        print(f"\n{split} (total {total}):")
        for cls in unified_classes:
            print(f"  {cls}: {counts[split][cls]}")


if __name__ == "__main__":
    main()
