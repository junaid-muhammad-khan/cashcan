"""Cheap on-device 'is there a face worth sending?' check, so we don't upload empty frames.
The server still does the real detection and matching."""
from __future__ import annotations

import cv2
import numpy as np


class HaarFaceDetector:
    def __init__(self, min_face_px: int = 80, detect_width: int = 320):
        if not hasattr(cv2, "CascadeClassifier"):  # removed in OpenCV 5
            raise RuntimeError("This OpenCV build has no CascadeClassifier (use opencv-python-headless<5)")
        self._cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        if self._cascade.empty():
            raise RuntimeError("Could not load the Haar cascade shipped with OpenCV")
        self._min, self._width = min_face_px, detect_width

    def has_face(self, frame: np.ndarray) -> bool:
        h, w = frame.shape[:2]
        scale = min(1.0, self._width / w)
        small = cv2.cvtColor(cv2.resize(frame, (int(w * scale), int(h * scale))), cv2.COLOR_BGR2GRAY)
        faces = self._cascade.detectMultiScale(small, scaleFactor=1.2, minNeighbors=3,
                                               minSize=(max(int(self._min * scale), 20),) * 2)
        return len(faces) > 0


class AlwaysDetector:
    """Fallback: no local pre-check. Frames are still rate-limited by the loop, and the server
    does the real detection, so this only costs bandwidth."""

    def has_face(self, frame: np.ndarray) -> bool:
        return True


def make_detector(min_face_px: int = 80, warn=print):
    try:
        return HaarFaceDetector(min_face_px)
    except RuntimeError as e:
        warn(f"cashcan_pi: local face pre-check disabled ({e}); sending every frame at the send interval")
        return AlwaysDetector()
