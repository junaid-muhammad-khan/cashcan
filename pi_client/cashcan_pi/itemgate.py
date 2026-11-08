"""Is an item being presented? Decided from the same camera, without a second sensor.

Watches a region of interest (where items are held or dropped) against a background of the empty view. An item counts when that region
differs from the background AND has stopped moving for `settle` seconds; it fires once, then waits until the region clears again.
Pure state machine (frame + time in, bool out), so it is testable without a camera.

Needs tuning on the real hardware: set the ROI to the item tray / opening area and check `min_fg` and `diff` in the real light.
"""
from __future__ import annotations

import cv2
import numpy as np


class ItemGate:
    def __init__(self, roi=(0.15, 0.40, 0.85, 1.0), diff: int = 28, min_fg: float = 0.10, clear_fg: float = 0.04,
                 still: float = 3.5, settle: float = 0.6, clear_for: float = 1.0, max_present: float = 30.0,
                 learn: float = 0.03, warmup: float = 1.0):
        self.roi, self.diff, self.min_fg, self.clear_fg = roi, diff, min_fg, clear_fg
        self.still, self.settle, self.clear_for, self.max_present = still, settle, clear_for, max_present
        self.learn, self.warmup = learn, warmup
        self._bg: np.ndarray | None = None
        self._prev: np.ndarray | None = None
        self._state = "empty"           # empty -> present (after firing) -> empty
        self._since: float | None = None  # when the current candidate / clear condition started
        self._start: float | None = None
        self._present_at = 0.0

    def crop(self, frame: np.ndarray) -> np.ndarray:
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = self.roi
        return frame[int(y1 * h):int(y2 * h), int(x1 * w):int(x2 * w)]

    def _gray(self, frame: np.ndarray) -> np.ndarray:
        """Small blurred COLOUR copy of the region (named _gray for history). Colour, not luminance: a red can on a grey tray
        has almost the same brightness but a very different colour."""
        return cv2.GaussianBlur(cv2.resize(self.crop(frame), (96, 72)), (5, 5), 0).astype(np.float32)

    @property
    def state(self) -> str:
        return self._state

    def step(self, frame: np.ndarray, now: float) -> bool:
        """True exactly once per item, when it has settled in the region."""
        g = self._gray(frame)
        if self._start is None:
            self._start = now
        if self._bg is None or (self._state == "empty" and now - self._start < self.warmup):
            self._bg = g if self._bg is None else 0.7 * self._bg + 0.3 * g   # assume the bin is empty at start-up
            self._prev = g
            return False
        fg = float((np.abs(g - self._bg).max(axis=2) > self.diff).mean())
        motion = float(np.abs(g - self._prev).mean())
        self._prev = g

        if self._state == "empty":
            if fg >= self.min_fg and motion <= self.still:
                self._since = self._since if self._since is not None else now
                if now - self._since >= self.settle:
                    self._state, self._since, self._present_at = "present", None, now
                    return True
            else:
                self._since = None
                if fg < self.clear_fg:  # nothing there: let the background follow slow light changes
                    self._bg = (1 - self.learn) * self._bg + self.learn * g
            return False

        # present: wait for the region to clear (or give up and re-learn the background if something is stuck there)
        if fg < self.clear_fg:
            self._since = self._since if self._since is not None else now
            if now - self._since >= self.clear_for:
                self._state, self._since = "empty", None
        else:
            self._since = None
            if now - self._present_at > self.max_present:
                self._bg, self._state = g, "empty"
        return False
