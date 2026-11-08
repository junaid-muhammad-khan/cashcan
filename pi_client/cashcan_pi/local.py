"""Identify people ON THE BIN: no network call per frame.

LocalApi has the same three methods the identity loop already calls on FaceApi (match, liveness_frame, session), but answers them
on the device: it detects and embeds the face with the same ONNX models the server uses, matches against a local copy of the gallery,
and runs the same head-turn challenge and session logic (the face_api classes, imported, so the rules cannot drift apart).
A frame costs ~25 ms here instead of 0.5-4 s through the server; it keeps working if the network drops (the gallery is cached on disk).

The gallery (everyone's face templates) is downloaded from the server with the bin key, refreshed every `refresh` seconds, and
only resent when it changed. Treat the bin as a trusted device: it holds biometric templates, so protect its key and its disk.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import time
from pathlib import Path

import cv2
import httpx
import numpy as np


def _face_api_modules():
    """Import the server's own modules (app.*) so quality gates, matching, liveness and sessions are identical. They live in ../face_api."""
    here = Path(__file__).resolve().parents[2] / "face_api"
    root = Path(os.environ.get("CASHCAN_FACE_API_DIR", here))
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from app import config  # noqa: PLC0415
    from app.face_engine import QualityError, check_quality, decode_image, pick_face  # noqa: PLC0415
    from app.lean_engine import LeanEngine  # noqa: PLC0415
    from app.liveness import LivenessManager  # noqa: PLC0415
    from app.matching import match  # noqa: PLC0415
    from app.sessions import SessionManager  # noqa: PLC0415
    from app.smoothing import EmbeddingSmoother  # noqa: PLC0415

    return dict(config=config, QualityError=QualityError, check_quality=check_quality, decode_image=decode_image, pick_face=pick_face,
                LeanEngine=LeanEngine, LivenessManager=LivenessManager, match=match, SessionManager=SessionManager, EmbeddingSmoother=EmbeddingSmoother)


class Gallery:
    """Local copy of the face templates: owners (one entry per template) and a matrix, refreshed from the server and cached on disk."""

    def __init__(self, http: httpx.Client | None = None, cache: Path | None = None, refresh: float = 60.0, clock=time.monotonic):
        self.http, self.refresh, self._clock = http, refresh, clock
        self.cache = cache or Path.home() / ".cashcan" / "gallery.json"
        self.owners: list[str] = []
        self.mat = np.zeros((0, 512), np.float32)
        self.version: str | None = None
        self._next = 0.0
        self._load_cache()

    def parse(self, body: dict) -> None:
        owners, rows = [], []
        for p in body["people"]:
            m = np.frombuffer(base64.b64decode(p["embeddings_b64"]), np.float16).reshape(-1, body.get("dim", 512)).astype(np.float32)
            m /= np.maximum(np.linalg.norm(m, axis=1, keepdims=True), 1e-9)   # float16 rounding: re-normalise
            owners += [p["user_id"]] * len(m)
            rows.append(m)
        self.owners, self.version = owners, body["version"]
        self.mat = np.concatenate(rows) if rows else np.zeros((0, body.get("dim", 512)), np.float32)

    def _load_cache(self) -> None:
        try:
            self.parse(json.loads(self.cache.read_text()))
        except (OSError, ValueError, KeyError):
            pass

    def maybe_refresh(self, now: float | None = None) -> bool:
        """Fetch the gallery if it is time. Network trouble keeps the current copy. True if the gallery changed."""
        now = self._clock() if now is None else now
        if self.http is None or now < self._next:
            return False
        self._next = now + self.refresh
        try:
            r = self.http.get("/gallery", headers={"If-None-Match": self.version} if self.version else {}, timeout=15)
            if r.status_code == 304:
                return False
            r.raise_for_status()
            body = r.json()
        except (httpx.HTTPError, ValueError):
            self._next = now + 10.0         # try again soon; keep identifying from the copy we have
            return False
        self.parse(body)
        try:
            self.cache.parent.mkdir(parents=True, exist_ok=True)
            self.cache.write_text(json.dumps(body))
        except OSError:
            pass
        return True

    def embeddings_for(self, user_id: str) -> np.ndarray:
        idx = [i for i, o in enumerate(self.owners) if o == user_id]
        return self.mat[idx] if idx else np.zeros((0, self.mat.shape[1]), np.float32)


class LocalApi:
    def __init__(self, gallery: Gallery, engine=None, smooth: int = 3, clock=time.monotonic, require_liveness: bool | None = None):
        m = _face_api_modules()
        self._m, self.gallery, self._clock = m, gallery, clock
        self.engine = engine or m["LeanEngine"]()
        self.sessions = m["SessionManager"](clock=clock)
        self.liveness = m["LivenessManager"](clock=clock)
        self.smoother = m["EmbeddingSmoother"](size=smooth, clock=clock)
        self.require_liveness = m["config"].REQUIRE_LIVENESS if require_liveness is None else require_liveness

    # ---- the three calls BinLoop makes
    def _face(self, jpeg: bytes):
        img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise self._m["QualityError"]("Could not read the image.")
        face = self._m["pick_face"](self.engine.analyse(img))
        self._m["check_quality"](face, identification=True)   # the lenient identification tier, as on the server
        return face

    def match(self, jpeg: bytes, session_token: str | None = None) -> dict:
        m, cfg = self._m, self._m["config"]
        self.gallery.maybe_refresh()
        try:
            face = self._face(jpeg)
        except m["QualityError"] as e:
            self.smoother.reset() if "face" in str(e).lower() else None
            return {"matched": False, "reason": "bad_frame", "message": str(e)}
        emb, _ = self.smoother.add(face.embedding)          # steadier than a single frame; resets if a different person steps in
        res = m["match"](emb, self.gallery.owners, self.gallery.mat)
        if not res.matched:
            return {"matched": False, "reason": res.reason, "score": round(res.score, 3)}
        base = {"matched": True, "user_id": res.user_id, "score": round(res.score, 3)}
        if not self.require_liveness:
            token, ttl = self.sessions.open(res.user_id)
            return {**base, "session_token": token, "expires_in": ttl}
        if session_token:
            known = self.sessions.live_age(session_token)
            if known and known[0] == res.user_id and known[1] <= cfg.LIVENESS_VALID_SECONDS:
                token, ttl = self.sessions.open(res.user_id, live_at=self.sessions.live_at(session_token))
                return {**base, "session_token": token, "expires_in": ttl}
        cid, direction, ttl = self.liveness.create(res.user_id)
        return {**base, "liveness_required": True, "challenge_id": cid, "direction": direction, "expires_in": ttl,
                "hint": f"Look straight at the camera, then turn your head to your {direction}."}

    def liveness_frame(self, challenge_id: str, jpeg: bytes) -> dict:
        user_id = self.liveness.user_for(challenge_id)
        if user_id is None:
            return {"status": "failed", "reason": "unknown_or_expired"}
        try:
            face = self._face(jpeg)
        except self._m["QualityError"] as e:
            return {"status": "pending", "hint": str(e)}
        gallery = self.gallery.embeddings_for(user_id)
        sim = float((gallery @ face.embedding).max()) if len(gallery) else None
        st = self.liveness.submit(challenge_id, face.turn, sim)
        if st.status == "passed":
            token, ttl = self.sessions.open(user_id)
            return {"status": "passed", "user_id": user_id, "session_token": token, "expires_in": ttl}
        return {k: v for k, v in (("status", st.status), ("hint", st.hint), ("reason", st.reason)) if v}

    def session(self, token: str) -> dict | None:
        user = self.sessions.user_for(token)
        return None if user is None else {"user_id": user, "wallet": None}   # the wallet is resolved server-side from the user id when paying

    def warm(self) -> bool:
        return True
