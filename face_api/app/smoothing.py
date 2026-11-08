"""Judge a person on the average of their last few good frames, not one frame.

A single frame is noisy (blink, motion, a lighting flicker): one frame of a clearly enrolled person can dip below the threshold.
The mean of the last N face templates is steadier. Safety: the window is cleared when the face disappears for a moment, or when a
new frame looks like a different person than the window (so a stranger stepping in cannot borrow someone else's average).
"""
from __future__ import annotations

import time
from collections import deque

import numpy as np


class EmbeddingSmoother:
    def __init__(self, size: int = 5, reset_below: float = 0.30, gap_seconds: float = 1.0, clock=time.monotonic):
        self._buf: deque[np.ndarray] = deque(maxlen=max(size, 1))
        self._reset_below, self._gap, self._clock = reset_below, gap_seconds, clock
        self._last: float | None = None

    def reset(self) -> None:
        self._buf.clear()

    def add(self, emb: np.ndarray) -> tuple[np.ndarray, int]:
        """Add one good frame. Returns (normalised mean template, frames averaged)."""
        now = self._clock()
        if self._last is not None and now - self._last > self._gap:
            self._buf.clear()                       # the face was gone for a moment: start over
        if self._buf:
            mean = np.mean(self._buf, axis=0)
            if float((mean / np.linalg.norm(mean)) @ emb) < self._reset_below:
                self._buf.clear()                   # looks like someone else: do not average the two people together
        self._buf.append(emb)
        self._last = now
        mean = np.mean(self._buf, axis=0)
        return (mean / np.linalg.norm(mean)).astype(np.float32), len(self._buf)
