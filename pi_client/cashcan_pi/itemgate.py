"""Is an item being presented? Decided from the same camera, without a second sensor.

Watches a region of interest (where items are held or dropped) against a background of the empty view. An item counts when that region
differs from the background AND has stopped moving for `settle` seconds; it fires once, then waits until the region clears again.
Pure state machine (frame + time in, bool out), so it is testable without a camera.

Needs tuning on the real hardware: set the ROI to the item tray / opening area and check `min_item` and `diff` in the real light.
"""
from __future__ import annotations

import cv2
import numpy as np


class ItemGate:
    def __init__(self, roi=(0.15, 0.40, 0.85, 1.0), diff: int = 28, min_item: float = 0.012, clear_item: float = 0.006,
                 still: float = 6.0, settle: float = 0.5, clear_for: float = 1.0, max_present: float = 30.0,
                 learn: float = 0.03, warmup: float = 1.0, max_fg: float = 0.80):
        self.roi, self.diff, self.min_item, self.clear_item = roi, diff, min_item, clear_item   # as fractions of the box: the biggest changed blob that counts as an item / as gone
        self.still, self.settle, self.clear_for, self.max_present = still, settle, clear_for, max_present
        self.learn, self.warmup, self.max_fg = learn, warmup, max_fg   # max_fg: more of the box than this changed = a person stepping in, not an item
        self.stats = {"fg": 0.0, "big": 0.0, "motion": 0.0}   # latest numbers, for the 'why' line in the preview
        self._mask: np.ndarray | None = None   # which small-resolution pixels differ from the empty view, from the latest step
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

    def item_crop(self, frame: np.ndarray, margin: float = 0.12, min_side: int = 64) -> np.ndarray:
        """A square crop tightly around what changed in the box (the item), instead of the whole box. The classifier then sees the item, not a
        wide picture of the desk with a small item somewhere in it. Falls back to the whole box if nothing stands out."""
        m = self._mask
        if m is None:
            return self.crop(frame)
        # open removes speckle; dilate joins the pieces of one item (a white bottle on a pale desk changes only in patches) before picking the biggest blob
        clean = cv2.dilate(cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)), np.ones((7, 7), np.uint8))
        n, _, stats, _ = cv2.connectedComponentsWithStats(clean)
        if n <= 1:
            return self.crop(frame)
        i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        x, y, w, h = (int(v) for v in stats[i, :4])
        H, W = frame.shape[:2]
        rx1, ry1 = int(self.roi[0] * W), int(self.roi[1] * H)
        sx, sy = (int(self.roi[2] * W) - rx1) / m.shape[1], (int(self.roi[3] * H) - ry1) / m.shape[0]
        cx, cy = rx1 + (x + w / 2) * sx, ry1 + (y + h / 2) * sy
        side = max(max(w * sx, h * sy) * (1 + 2 * margin), min_side)
        x1, x2 = int(max(0, cx - side / 2)), int(min(W, cx + side / 2))
        y1, y2 = int(max(0, cy - side / 2)), int(min(H, cy + side / 2))
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return self.crop(frame)
        d = abs(crop.shape[0] - crop.shape[1])   # pad to a square so the item is not stretched when it is resized for the classifier
        if d:
            a, b = d // 2, d - d // 2
            crop = cv2.copyMakeBorder(crop, *( (a, b, 0, 0) if crop.shape[0] < crop.shape[1] else (0, 0, a, b) ), cv2.BORDER_REPLICATE)
        return crop

    def _gray(self, frame: np.ndarray) -> np.ndarray:
        """Small blurred COLOUR copy of the region (named _gray for history). Colour, not luminance: a red can on a grey tray
        has almost the same brightness but a very different colour."""
        return cv2.GaussianBlur(cv2.resize(self.crop(frame), (96, 72)), (5, 5), 0).astype(np.float32)

    @property
    def why(self) -> str:
        """In plain words, what the gate is waiting for (shown in the preview window)."""
        st = self.stats
        if self._bg is None or self._start is None:
            return "learning the empty view"
        if self._state == "present":
            return "item in the box"
        if st["big"] < self.min_item:
            return f"nothing new in the box (change {st['big'] * 100:.1f}%, needs {self.min_item * 100:.1f}%)"
        if st["fg"] > self.max_fg:
            return "most of the box changed: looks like a person, not an item"
        if st["motion"] > self.still:
            return "item is moving: hold it still"
        return "settling..."

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
        self._mask = np.abs(g - self._bg).max(axis=2) > self.diff
        fg = float(self._mask.mean())                    # how much of the box changed in total (a person fills most of it)
        n, _, stats, _ = cv2.connectedComponentsWithStats(cv2.morphologyEx(self._mask.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)))
        big = float(stats[1:, cv2.CC_STAT_AREA].max()) / self._mask.size if n > 1 else 0.0   # the biggest changed blob: a can or bottle is a small blob
        motion = float(np.abs(g - self._prev).mean())
        self._prev = g
        self.stats = {"fg": fg, "big": big, "motion": motion}

        if self._state == "empty":
            if big >= self.min_item and fg <= self.max_fg and motion <= self.still:
                self._since = self._since if self._since is not None else now
                if now - self._since >= self.settle:
                    self._state, self._since, self._present_at = "present", None, now
                    return True
            else:
                self._since = None
                if big < self.clear_item:  # nothing there: let the background follow slow light changes
                    self._bg = (1 - self.learn) * self._bg + self.learn * g
            return False

        # present: wait for the region to clear (or give up and re-learn the background if something is stuck there)
        if big < self.clear_item:
            self._since = self._since if self._since is not None else now
            if now - self._since >= self.clear_for:
                self._state, self._since = "empty", None
        else:
            self._since = None
            if now - self._present_at > self.max_present:
                self._bg, self._state = g, "empty"
        return False
