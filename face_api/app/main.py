"""CashCan face API.

GET    /                  enrollment web page
POST   /enroll            consent + 3-8 face frames + wallet -> stores embeddings only
POST   /match             one frame from the bin camera -> user + (challenge | session token)
POST   /liveness/{id}/frame  frames answering a head-turn challenge -> session token when passed
GET    /session/{token}   which user a live session belongs to (used by the payout step)
DELETE /users/{user_id}   delete all biometric data for a user
"""
from __future__ import annotations

import re

from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from . import config
from .face_engine import FaceEngine, InsightFaceEngine, QualityError, check_quality, decode_image, pick_face
from .liveness import LivenessManager
from .matching import match
import numpy as np
from .sessions import SessionManager
from .store import FaceStore

USER_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
SOLANA_ADDR_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")  # base58 public key
STATIC = Path(__file__).parent / "static"


def create_app(engine: FaceEngine | None = None, store: FaceStore | None = None,
               sessions: SessionManager | None = None, liveness: LivenessManager | None = None) -> FastAPI:
    app = FastAPI(title="CashCan face API")
    state = {"engine": engine, "store": store or FaceStore(config.DB_PATH),
             "sessions": sessions or SessionManager(), "liveness": liveness or LivenessManager()}

    def get_engine() -> FaceEngine:
        if state["engine"] is None:  # lazy: model load is slow
            state["engine"] = InsightFaceEngine()
        return state["engine"]

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.post("/enroll")
    async def enroll(user_id: str = Form(...), wallet: str = Form(...), consent: bool = Form(False),
                     frames: list[UploadFile] = File(...)):
        if not consent:
            raise HTTPException(400, "Consent is required to store a face embedding.")
        if not USER_ID_RE.match(user_id):
            raise HTTPException(400, "user_id must be 1-64 letters, digits, '.', '_' or '-'.")
        wallet = wallet.strip()
        if not SOLANA_ADDR_RE.match(wallet):
            raise HTTPException(400, "That does not look like a Solana wallet address.")
        if state["store"].user_exists(user_id):
            raise HTTPException(409, "User already enrolled. Delete first to re-enroll.")
        if not config.MIN_ENROLL_FRAMES <= len(frames) <= config.MAX_ENROLL_FRAMES:
            raise HTTPException(400, f"Send {config.MIN_ENROLL_FRAMES}-{config.MAX_ENROLL_FRAMES} frames.")

        embeddings, problems = [], []
        for i, f in enumerate(frames):
            try:
                face = pick_face(get_engine().analyse(decode_image(await f.read())))
                check_quality(face)
                embeddings.append(face.embedding)
            except QualityError as e:
                problems.append(f"frame {i + 1}: {e}")
        if len(embeddings) < config.MIN_ENROLL_FRAMES:
            raise HTTPException(422, {"message": "Not enough usable frames.", "problems": problems})

        state["store"].add_user(user_id, wallet, embeddings)
        return {"enrolled": True, "user_id": user_id, "frames_used": len(embeddings), "problems": problems}

    @app.post("/match")
    async def match_face(frame: UploadFile = File(...), session_token: str | None = Form(None)):
        """Identify the face. With liveness on, a match returns a challenge instead of a session;
        finish it via POST /liveness/{challenge_id}/frame. Passing the current live session_token
        lets the same person refresh without a new challenge, for LIVENESS_VALID_SECONDS only."""
        try:
            face = pick_face(get_engine().analyse(decode_image(await frame.read())))
            check_quality(face)
        except QualityError as e:
            return {"matched": False, "reason": "bad_frame", "message": str(e)}
        owners, gallery = state["store"].all_embeddings()
        res = match(face.embedding, owners, gallery)
        if not res.matched:
            return {"matched": False, "reason": res.reason, "score": round(res.score, 3)}
        base = {"matched": True, "user_id": res.user_id, "score": round(res.score, 3)}

        if not config.REQUIRE_LIVENESS:
            token, ttl = state["sessions"].open(res.user_id)
            return {**base, "session_token": token, "expires_in": ttl}
        if session_token:  # continuity: same person, liveness proven recently
            known = state["sessions"].live_age(session_token)
            if known and known[0] == res.user_id and known[1] <= config.LIVENESS_VALID_SECONDS:
                live_at = state["sessions"].live_at(session_token)
                token, ttl = state["sessions"].open(res.user_id, live_at=live_at)
                return {**base, "session_token": token, "expires_in": ttl}
        cid, direction, ttl = state["liveness"].create(res.user_id)
        return {**base, "liveness_required": True, "challenge_id": cid, "direction": direction,
                "expires_in": ttl, "hint": f"Look straight at the camera, then turn your head to your {direction}."}

    @app.post("/liveness/{challenge_id}/frame")
    async def liveness_frame(challenge_id: str, frame: UploadFile = File(...)):
        user_id = state["liveness"].user_for(challenge_id)
        if user_id is None:  # unknown, expired or already finished
            return {"status": "failed", "reason": "unknown_or_expired"}
        try:
            face = pick_face(get_engine().analyse(decode_image(await frame.read())))
            check_quality(face)
        except QualityError as e:  # unusable frame: not evidence either way
            return {"status": "pending", "hint": str(e)}
        gallery = state["store"].embeddings_for(user_id)
        sim = float((gallery @ face.embedding).max()) if len(gallery) else None
        st = state["liveness"].submit(challenge_id, face.turn, sim)
        if st.status == "passed":
            token, ttl = state["sessions"].open(user_id)
            return {"status": "passed", "user_id": user_id, "session_token": token, "expires_in": ttl}
        return {k: v for k, v in (("status", st.status), ("hint", st.hint), ("reason", st.reason)) if v}

    @app.get("/session/{token}")
    def session(token: str):
        user_id = state["sessions"].user_for(token)
        if user_id is None:
            raise HTTPException(404, "Session expired or unknown.")
        return {"user_id": user_id, "wallet": state["store"].wallet(user_id)}

    @app.delete("/users/{user_id}")
    def delete_user(user_id: str):
        if not state["store"].delete_user(user_id):
            raise HTTPException(404, "No such user.")
        state["sessions"].close_user(user_id)
        return {"deleted": True}

    return app


def app_factory() -> FastAPI:
    return create_app()
