"""
Sample representative images from data/processed/train to build models/calibration.txt,
the calibration dataset list RKNN-Toolkit2 needs for INT8 quantization (see convert_rknn.py).

Run from ml/: python scripts/generate_calibration_list.py
"""
import random
from pathlib import Path

SEED = 42
N_PER_CLASS = 60  # ~180 total across 3 classes; RKNN docs suggest 100-500 calibration images

ML_ROOT = Path(__file__).resolve().parent.parent
TRAIN_DIR = ML_ROOT / "data" / "processed" / "train"
MODELS_DIR = ML_ROOT / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)


def main():
    random.seed(SEED)
    lines = []
    for class_dir in sorted(TRAIN_DIR.iterdir()):
        if not class_dir.is_dir():
            continue
        images = sorted(class_dir.glob("*"))
        sample = random.sample(images, min(N_PER_CLASS, len(images)))
        lines.extend(str(p.resolve()) for p in sample)

    out_path = MODELS_DIR / "calibration.txt"
    out_path.write_text("\n".join(lines) + "\n")
    print(f"Wrote {len(lines)} calibration image paths to {out_path}")


if __name__ == "__main__":
    main()
