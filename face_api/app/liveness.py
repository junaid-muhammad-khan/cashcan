"""Active liveness: a random head-turn challenge.

Why this resists a photo or screen held up to the camera
- The challenge direction is random and issued only after a face is recognised, so a fixed recording
  has a 50% chance to be wrong, and the attacker must already be holding a photo that matches someone.
- The measure is the nose's sideways offset from the eye midpoint, divided by the eye distance
  (``turn_ratio``). On a real 3D head the nose sticks out, so turning the head shifts it a lot. On a
  flat photo, even if tilted, all features scale together and the ratio barely moves.
- Every frame must still look like the same enrolled person, so swapping people mid-challenge fails.

What it does NOT stop: a video of the right person turning the right way, a 3D mask, or a deepfake
played into the camera. Say so when presenting. It raises the cost of abuse; it is not proof of life.

Convention: the camera image is NOT mirrored. Positive ratio = nose toward the image's right =
the user turned to *their own left*.
"""
from __future__ import annotations

import random
import secrets
import time
from dataclasses import dataclass, field

import numpy as np

from . import config

DIRECTIONS = ("left", "right")  # from the user's point of view


def turn_ratio(kps: np.ndarray) -> float:
    """kps: 5x2 InsightFace landmarks (eye, eye, nose, mouth, mouth), image coordinates.
    Roll-invariant: projects the nose offset onto the eye axis."""
    l, r, nose = kps[0], kps[1], kps[2]
    axis = r - l
    iod = float(np.linalg.norm(axis))
    if iod < 1e-6:
        return 0.0
    return float(((nose - (l + r) / 2) @ (axis / iod)) / iod)


@dataclass
class Challenge:
    user_id: str
    direction: str
    expires_at: float
    seen_center: bool = False
    strikes: int = 0


@dataclass
class Status:
    status: str            # pending | passed | failed
    hint: str = ""
    reason: str = ""       # set when failed
    user_id: str | None = None


def prompt_for(direction: str) -> str:
    return f"Now turn your head to your {direction}, then hold."


class LivenessManager:
    def __init__(self, clock=time.monotonic, rng: random.Random | None = None):
        self._clock, self._rng = clock, rng or random.SystemRandom()
        self._open: dict[str, Challenge] = {}

    def _sweep(self) -> None:
        now = self._clock()
        for cid in [c for c, ch in self._open.items() if now > ch.expires_at]:
            del self._open[cid]

    def create(self, user_id: str) -> tuple[str, str, float]:
        self._sweep()
        if len(self._open) >= config.LIVENESS_MAX_OPEN:  # drop the oldest rather than grow without bound
            del self._open[min(self._open, key=lambda c: self._open[c].expires_at)]
        cid, direction = secrets.token_urlsafe(12), self._rng.choice(DIRECTIONS)
        self._open[cid] = Challenge(user_id, direction, self._clock() + config.LIVENESS_TTL_SECONDS)
        return cid, direction, config.LIVENESS_TTL_SECONDS

    def user_for(self, cid: str) -> str | None:
        ch = self._open.get(cid)
        return ch.user_id if ch else None

    def direction_for(self, cid: str) -> str | None:
        ch = self._open.get(cid)
        return ch.direction if ch else None

    def submit(self, cid: str, turn: float | None, id_similarity: float | None) -> Status:
        """One analysed frame. id_similarity = best cosine vs the claimed user's enrolled embeddings."""
        ch = self._open.get(cid)
        if ch is None:
            return Status("failed", reason="unknown_or_expired")
        if self._clock() > ch.expires_at:
            del self._open[cid]
            return Status("failed", reason="expired", user_id=ch.user_id)

        if id_similarity is None or id_similarity < config.LIVENESS_ID_THRESHOLD:
            ch.strikes += 1
            if ch.strikes >= config.LIVENESS_MAX_STRIKES:
                del self._open[cid]
                return Status("failed", reason="different_person", user_id=ch.user_id)
            return Status("pending", hint="Look at the camera.")
        if turn is None:
            return Status("pending", hint="Look at the camera.")

        signed = turn if ch.direction == "left" else -turn  # >0 means turned the asked way
        if not ch.seen_center:
            if abs(turn) <= config.LIVENESS_CENTER_MAX:
                ch.seen_center = True
                return Status("pending", hint=prompt_for(ch.direction))
            return Status("pending", hint="Look straight at the camera.")
        if signed >= config.LIVENESS_TURN_MIN:
            del self._open[cid]
            return Status("passed", user_id=ch.user_id)
        return Status("pending", hint=prompt_for(ch.direction))
