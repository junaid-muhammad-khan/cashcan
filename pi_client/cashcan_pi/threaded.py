"""Run the identity loop (network calls to the face server) on its own thread, so the camera and the preview never wait on it.

The camera loop hands over its newest frame and carries on; the worker takes the latest frame at its own pace (each server call
can take 0.5-4 s) and updates the session. Everything the rest of the bin reads (session, status) is plain attribute reads.
"""
from __future__ import annotations

import threading
import time


class BackgroundIdentity:
    def __init__(self, loop, idle_sleep: float = 0.02):
        self.loop, self._idle = loop, idle_sleep
        self._frame = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="identity", daemon=True)
        self._thread.start()

    # --- same surface the controller uses
    def step(self, frame, now: float) -> None:
        with self._lock:
            self._frame = frame          # newest frame wins; older ones are simply dropped

    def current_session(self, now: float):
        s = self.loop._session            # read only: expiry is enforced by the worker's own steps
        return s if s is not None and now <= s.expires_at else None

    def info(self) -> dict:
        return {"face_seen": self.loop.face_seen, "last_reply": self.loop.last_reply}

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)

    def _run(self) -> None:
        while not self._stop.is_set():
            with self._lock:
                frame, self._frame = self._frame, None
            if frame is None:
                time.sleep(self._idle)
                continue
            try:
                self.loop.step(frame, time.monotonic())   # may block on the network; nobody else is waiting for it
            except Exception as e:                         # never let the worker die silently
                self.loop.emit({"event": "error", "message": f"identity worker: {type(e).__name__}: {e}"})
                time.sleep(0.5)
