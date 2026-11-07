"""The bin's identity loop. step() is a pure-ish state machine (frame + time in, events out),
so it is testable without a camera, a network or a clock.

Rules
- Only send a frame when the cheap local detector sees a face, and not faster than send_interval.
- A match opens a session (token from the server). Payout code reads current_session().
- While a session is open, re-check the face every recheck_interval. A different person, or two
  unknown/denied checks in a row, ends the session. A bad frame (blur, no face) does not.
- Network trouble never crashes the loop: show an error, back off, keep going.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import cv2
import httpx
import numpy as np


@dataclass
class Session:
    user_id: str
    wallet: str | None
    token: str
    expires_at: float


Event = dict


class BinLoop:
    def __init__(self, api, detector, indicator, on_event: Callable[[Event], None] = lambda e: None,
                 send_interval: float = 0.7, recheck_interval: float = 5.0, denied_cooldown: float = 2.0,
                 error_backoff: float = 3.0, idle_probe_interval: float = 3.0, max_width: int = 640):
        self.api, self.detector, self.ind, self.emit = api, detector, indicator, on_event
        self.send_interval, self.recheck_interval = send_interval, recheck_interval
        self.denied_cooldown, self.error_backoff, self.max_width = denied_cooldown, error_backoff, max_width
        self.idle_probe_interval = idle_probe_interval
        self._next_probe: float | None = None
        self._session: Session | None = None
        self._next_send = 0.0
        self._next_recheck = 0.0
        self._denials = 0
        self._last_error_emit = -1e9

    def current_session(self, now: float) -> Session | None:
        if self._session and now > self._session.expires_at:
            self._end("expired")
        return self._session

    # -- internals
    def _end(self, why: str) -> None:
        if self._session:
            self.emit({"event": "session_ended", "user_id": self._session.user_id, "why": why})
        self._session, self._denials = None, 0
        self.ind.set("idle")

    def _jpeg(self, frame: np.ndarray) -> bytes:
        h, w = frame.shape[:2]
        if w > self.max_width:
            frame = cv2.resize(frame, (self.max_width, int(h * self.max_width / w)))
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        if not ok:
            raise RuntimeError("JPEG encode failed")
        return buf.tobytes()

    def step(self, frame: np.ndarray, now: float) -> None:
        self.current_session(now)  # expire first
        if now < self._next_send:
            return
        if self._session and now < self._next_recheck:
            return
        probe = not self.detector.has_face(frame)
        if probe:
            # The cheap detector is frontal-only and can miss a real face (tilt, glasses, odd light).
            # Fail open: send a probe frame now and then so a missed face costs a delay, not service.
            if self._next_probe is None:
                self._next_probe = now + self.idle_probe_interval
            if now < self._next_probe:
                if not self._session:
                    self.ind.set("idle")
                return
            self._next_probe = now + self.idle_probe_interval

        self._next_send = now + self.send_interval
        if not self._session and not probe:
            self.ind.set("scanning")
        try:
            res = self.api.match(self._jpeg(frame))
        except (httpx.HTTPError, ValueError) as e:  # network, bad status, bad JSON
            self._next_send = now + self.error_backoff
            self.ind.set("error", "cannot reach the server")
            if now - self._last_error_emit >= 10:
                self._last_error_emit = now
                self.emit({"event": "error", "message": f"{type(e).__name__}: {e}"})
            return
        self._handle(res, now, probe)

    def _handle(self, res: dict, now: float, probe: bool = False) -> None:
        if res.get("matched"):
            self._denials = 0
            user = res["user_id"]
            if self._session and self._session.user_id != user:
                self._end("different_person")
            try:
                info = self.api.session(res["session_token"]) or {}
            except httpx.HTTPError:
                info = {}
            is_new = self._session is None
            self._session = Session(user, info.get("wallet"), res["session_token"], now + res["expires_in"])
            self._next_recheck = now + self.recheck_interval
            self.ind.set("matched", user)
            if is_new:
                self.emit({"event": "session_started", "user_id": user, "wallet": self._session.wallet,
                           "token": self._session.token, "expires_in": res["expires_in"],
                           "score": res.get("score")})
            return

        reason = res.get("reason", "unknown")
        if reason == "bad_frame":  # blur / no usable face: not evidence of a different person
            if probe and not self._session:
                self.ind.set("idle")  # empty bin, nothing to tell the user
            else:
                self.ind.set("scanning", res.get("message", ""))
            return
        self._next_send = now + self.denied_cooldown
        self.ind.set("denied", reason)
        self.emit({"event": "denied", "reason": reason, "score": res.get("score")})
        if self._session:
            self._denials += 1
            if self._denials >= 2:
                self._end("unrecognised_face")
