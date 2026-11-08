"""
Live webcam demo for the YOLO11n-cls comparison model (see train_yolo11n.py), using
Ultralytics' own built-in webcam streaming/display instead of a custom OpenCV loop.
Press 'q' in the preview window to quit.

Run from ml/: python scripts/live_predict_yolo11n.py
"""
from pathlib import Path

from ultralytics import YOLO

ML_ROOT = Path(__file__).resolve().parent.parent
BEST_PT = ML_ROOT / "models" / "yolo11n_runs" / "train" / "weights" / "best.pt"

model = YOLO(str(BEST_PT))
# stream=True returns a generator - must iterate it, otherwise predict() never actually runs.
for result in model.predict(source=0, show=True, imgsz=224, stream=True, verbose=True):
    pass
