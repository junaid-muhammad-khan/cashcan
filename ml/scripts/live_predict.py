"""
Live webcam loop for trying out the CashCan classifier interactively.

Classifies continuously - just hold an item up, the overlay updates live, no key
needed. When it gets something wrong, press the correct label's key to save that exact
frame as a labeled correction (does NOT retrain anything - just saves the image for a
later patch, same idea as class_map.yaml's custom_tallcans entry):
  c = cans, o = organics, w = waste, q = quit

Usage: python scripts/live_predict.py
(First run will prompt for camera permission - allow it in System Settings > Privacy
& Security > Camera if the window doesn't show a feed.)
"""
import json
import time
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

ML_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ML_ROOT / "models"
CORRECTIONS_DIR = ML_ROOT / "data" / "raw" / "webcam_corrections"
IMG_SIZE = 224
SAVE_KEYS = {ord("c"): "cans", ord("o"): "organics", ord("w"): "waste"}

# Must match train.py's transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def softmax(x):
    e = np.exp(x - np.max(x))
    return e / e.sum()


def preprocess_frame(frame_bgr):
    # cv2 gives BGR; the model was trained on RGB (PIL/torchvision convention).
    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    resized = cv2.resize(rgb, (IMG_SIZE, IMG_SIZE), interpolation=cv2.INTER_LINEAR)
    arr = resized.astype(np.float32) / 255.0
    arr = (arr - MEAN) / STD
    arr = arr.transpose(2, 0, 1)  # HWC -> CHW
    return arr[np.newaxis, :, :, :].astype(np.float32)


def main():
    classes = json.loads((MODELS_DIR / "classes.json").read_text())
    session = ort.InferenceSession(str(MODELS_DIR / "mobilenetv2_cashcan.onnx"))

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        raise RuntimeError("Could not open webcam (index 0). Check camera permissions "
                            "in System Settings > Privacy & Security > Camera.")

    for cls in SAVE_KEYS.values():
        (CORRECTIONS_DIR / cls).mkdir(parents=True, exist_ok=True)

    last_result_text = ["Starting..."]
    last_printed_bin = None
    last_print_time = 0.0
    last_frame = None
    print("Webcam window opened. Classifying continuously.")
    print("Keys: c=save as cans, o=save as organics, w=save as waste, q=quit")

    while True:
        ok, frame = cap.read()
        if not ok:
            print("Failed to read frame from webcam")
            break

        input_tensor = preprocess_frame(frame)
        logits = session.run(None, {"input": input_tensor})[0][0]
        probs = softmax(logits)
        ranked = sorted(zip(classes, probs.tolist()), key=lambda x: -x[1])
        top_bin, top_conf = ranked[0]
        last_result_text = [f"{top_bin.upper()} ({top_conf:.1%})"] + \
                            [f"{name}: {p:.1%}" for name, p in ranked]

        # Print to the terminal only when the top prediction changes, or every 1s while
        # it's stable, so the console doesn't get flooded at camera frame rate.
        now = time.time()
        if top_bin != last_printed_bin or (now - last_print_time) > 1.0:
            print(f"\n{top_bin.upper()}  ({top_conf:.1%})  " +
                  "  ".join(f"{name}:{p:.0%}" for name, p in ranked))
            last_printed_bin = top_bin
            last_print_time = now

        last_frame = frame

        display = frame.copy()
        for i, line in enumerate(last_result_text):
            cv2.putText(display, line, (10, 30 + i * 28), cv2.FONT_HERSHEY_SIMPLEX,
                        0.7, (0, 255, 0), 2)
        cv2.putText(display, "c=cans o=organics w=waste q=quit", (10, display.shape[0] - 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
        cv2.imshow("CashCan - live classification, q to quit", display)

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        elif key in SAVE_KEYS:
            label = SAVE_KEYS[key]
            out_path = CORRECTIONS_DIR / label / f"webcam_{int(time.time() * 1000)}.jpg"
            cv2.imwrite(str(out_path), last_frame)
            print(f"Saved correction -> {label}: {out_path.name}")

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
