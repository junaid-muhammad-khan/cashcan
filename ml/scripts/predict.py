"""
Run the trained MobileNetV2 ONNX model on a single image. For actual Pi/RK3582 deployment,
convert to RKNN first (see convert_rknn.py) - this script is for testing on a laptop with
onnxruntime.

Usage: python scripts/predict.py path/to/image.jpg
Prints JSON: {"bin": ..., "confidence": ..., "top3": [{"bin": ..., "confidence": ...}, ...]}

Note: the model predicts a physical BIN (cans/organics/waste), not a raw material, since
CashCan's hardware only has 3 bin openings (see class_map.yaml). The output key is "bin"
to reflect that, not "material".
"""
import json
import sys
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image

ML_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ML_ROOT / "models"
IMG_SIZE = 224

# Must match train.py's transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def softmax(x):
    e = np.exp(x - np.max(x))
    return e / e.sum()


def preprocess(image_path):
    # Image.BILINEAR explicitly, to match torchvision.transforms.Resize's default
    # interpolation exactly (train.py's eval_tf) - PIL's own default resize filter differs
    # and introduces small train/inference skew otherwise.
    img = Image.open(image_path).convert("RGB").resize((IMG_SIZE, IMG_SIZE), Image.BILINEAR)
    arr = np.asarray(img, dtype=np.float32) / 255.0
    arr = (arr - MEAN) / STD
    arr = arr.transpose(2, 0, 1)  # HWC -> CHW
    return arr[np.newaxis, :, :, :].astype(np.float32)


def predict(image_path):
    classes = json.loads((MODELS_DIR / "classes.json").read_text())
    session = ort.InferenceSession(str(MODELS_DIR / "mobilenetv2_cashcan.onnx"))

    input_tensor = preprocess(image_path)
    logits = session.run(None, {"input": input_tensor})[0][0]
    probs = softmax(logits)

    ranked = sorted(zip(classes, probs.tolist()), key=lambda x: -x[1])
    return {
        "bin": ranked[0][0],
        "confidence": round(ranked[0][1], 4),
        "top3": [{"bin": name, "confidence": round(p, 4)} for name, p in ranked[:3]],
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/predict.py path/to/image.jpg", file=sys.stderr)
        sys.exit(1)
    result = predict(sys.argv[1])
    print(json.dumps(result, indent=2))
