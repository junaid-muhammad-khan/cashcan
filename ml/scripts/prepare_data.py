"""
Build train/val/test image folders from the raw datasets using class_map.yaml.

- train_val datasets (trashnet, gd) are split 80/20 into processed/train and processed/val.
- mixed datasets (realwaste) split off `train_fraction` of images into the same 80/20
  train/val split, and the rest into processed/test (genuinely held out, never trained on).
- train_only datasets (custom_tallcans) go entirely into processed/train, no val/test split -
  for small user-supplied patch sets with too few images to split meaningfully.
- test_only datasets (none currently) go entirely into processed/test.

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


def write_split(images, split, ds_name, unified_class, counts):
    dest_dir = PROCESSED / split / unified_class
    for img in images:
        shutil.copy2(img, dest_dir / f"{ds_name}_{img.name}")
        counts[split][unified_class] += 1


def write_train_val(images, ds_name, unified_class, counts):
    random.shuffle(images)
    n_val = max(1, int(len(images) * VAL_FRACTION))
    write_split(images[:n_val], "val", ds_name, unified_class, counts)
    write_split(images[n_val:], "train", ds_name, unified_class, counts)


def main():
    random.seed(SEED)
    class_map = yaml.safe_load((ML_ROOT / "class_map.yaml").read_text())
    unified_classes = class_map["unified_classes"]

    # Regenerate from scratch - stale files from a previous class_map.yaml/split config
    # would otherwise linger alongside the new ones.
    if PROCESSED.exists():
        shutil.rmtree(PROCESSED)
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
                write_train_val(images, ds_name, unified_class, counts)
            elif role == "test_only":
                write_split(images, "test", ds_name, unified_class, counts)
            elif role == "train_only":
                # All images go to train, none held out for val/test - used for small
                # user-supplied patch sets where there are too few originals to split.
                write_split(images, "train", ds_name, unified_class, counts)
            elif role == "mixed":
                random.shuffle(images)
                train_fraction = ds_cfg["train_fraction"]
                n_train_pool = int(len(images) * train_fraction)
                write_train_val(images[:n_train_pool], ds_name, unified_class, counts)
                write_split(images[n_train_pool:], "test", ds_name, unified_class, counts)
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
