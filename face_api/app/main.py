"""CashCan face API.

GET    /                  enrollment web page
POST   /enroll            consent + 3-8 face frames + wallet -> stores embeddings only
POST   /match             one frame from the bin camera -> user + (challenge | session token)
POST   /liveness/{id}/frame  frames answering a head-turn challenge -> session token when passed
GET    /session/{token}   which user a live session belongs to
DELETE /users/{user_id}   delete all biometric data for a user
GET    /rewards           the reward table (cents per item class), read-only
GET/PUT /me, GET /me/activity   signed-in profile and the user's drops (Auth0)
POST   /interactions      one sorted item from a bin (X-Bin-Key); the server decides the reward and pays it
GET    /cron/reconcile    retries failed payouts and resolves stuck ones (Vercel cron, CRON_SECRET)
GET    /game/leaderboard  the kids' sorting game: best scores (nicknames only; public)
POST   /game/scores       save a finished game (Auth0); the server works the score out itself
PUT    /game/nickname     the name shown on the game leaderboard (Auth0)
"""
from __future__ import annotations

import base64
import hashlib
import logging
import re
import secrets

from pathlib import Path

from fastapi import Body, FastAPI, File, Form, Header, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse

from . import config, rewards
from .activity import RANGES, summarise, window, zone
from .auth import TokenVerifier, bearer, bin_for_key
from .face_engine import FaceEngine, InsightFaceEngine, QualityError, check_quality, decode_image, pick_face
from .liveness import POSE_HINTS, LivenessManager, enroll_pose
from .matching import match
from .payouts import public
import numpy as np
from .sessions import SessionManager
from .store import FaceStore

USER_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
SOLANA_ADDR_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")  # base58 public key
STATIC = Path(__file__).parent / "static"
log = logging.getLogger("cashcan.match")
log.setLevel(logging.INFO)
if not logging.getLogger().handlers:  # make sure these lines reach the host's log (Vercel shows stdout/stderr)
    logging.basicConfig(level=logging.INFO)


def make_engine() -> FaceEngine:
    """The lean onnxruntime engine when the two model files are present (always, on Vercel), else the full insightface package."""
    from .lean_engine import LeanEngine, models_available

    return LeanEngine() if models_available() else InsightFaceEngine()


def make_store():
    """Databricks when configured (CASHCAN_STORE / DATABRICKS_* env), else the local SQLite file."""
    if config.STORE == "databricks":
        from .databricks_store import DatabricksFaces, DatabricksStore

        return DatabricksStore(DatabricksFaces())  # raises with a clear message if the env vars are missing
    return FaceStore(config.DB_PATH)


def make_accounts():
    """Accounts in Databricks when configured, else None (the account endpoints then answer 503)."""
    if config.STORE != "databricks":
        return None
    from .accounts import Accounts
    from .databricks_store import DatabricksFaces

    return Accounts(DatabricksFaces())


def make_payouts(accounts):
    """The payout service over the same Databricks connection as the accounts, else None."""
    if accounts is None:
        return None
    from .ledger import Ledger
    from .payouts import Payouts

    return Payouts(Ledger(accounts.db))


def make_game(accounts):
    """Game scores over the same Databricks connection as the accounts, else None."""
    if accounts is None:
        return None
    from .game import GameScores

    return GameScores(accounts.db)


def make_verifier():
    return TokenVerifier(config.AUTH0_DOMAIN, config.AUTH0_AUDIENCE) if config.AUTH0_DOMAIN and config.AUTH0_AUDIENCE else None


def create_app(engine: FaceEngine | None = None, store: FaceStore | None = None,
               sessions: SessionManager | None = None, liveness: LivenessManager | None = None,
               accounts=None, verifier=None, payouts=None, game=None) -> FastAPI:
    app = FastAPI(title="CashCan face API")

    @app.middleware("http")
    async def strip_mount_prefix(request, call_next):
        """Behind Vercel the API is mounted at /face-api and the prefix may reach us unstripped: accept both forms."""
        path = request.scope["path"]
        if path == config.MOUNT_PREFIX or path.startswith(config.MOUNT_PREFIX + "/"):
            request.scope["path"] = path[len(config.MOUNT_PREFIX):] or "/"
            if request.scope.get("raw_path"):
                request.scope["raw_path"] = request.scope["path"].encode()
        return await call_next(request)
    state = {"engine": engine, "store": store or make_store(),
             "sessions": sessions or SessionManager(), "liveness": liveness or LivenessManager(),
             "accounts": accounts or make_accounts(), "verifier": verifier or make_verifier()}
    state["payouts"] = payouts or make_payouts(state["accounts"])
    state["game"] = game or make_game(state["accounts"])

    def need_payouts():
        if state["payouts"] is None:
            raise HTTPException(503, "Interactions are not configured (needs the Databricks store).")
        return state["payouts"]

    def need_game():
        if state["game"] is None:
            raise HTTPException(503, "The game leaderboard is not configured (needs the Databricks store).")
        return state["game"]

    def need_accounts():
        if state["accounts"] is None:
            raise HTTPException(503, "Accounts are not configured (needs the Databricks store).")
        return state["accounts"]

    def current_user(token: str) -> dict:
        """The signed-in user from an Auth0 access token (created on first login)."""
        if state["verifier"] is None:
            raise HTTPException(503, "Login is not configured (set AUTH0_DOMAIN and AUTH0_AUDIENCE).")
        return need_accounts().get_or_create_user(state["verifier"].sub(token))

    def get_engine() -> FaceEngine:
        if state["engine"] is None:  # lazy: model load is slow
            state["engine"] = make_engine()
        return state["engine"]

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/warm")
    def warm():
        """Starts the function and loads the face models, so the first real request after idle is not slow."""
        get_engine()
        return {"warm": True}

    @app.post("/enroll")
    async def enroll(user_id: str = Form(""), wallet: str = Form(""), consent: bool = Form(False),
                     frames: list[UploadFile] = File(...), poses: str = Form(""), replace: bool = Form(False),
                     authorization: str | None = Header(None)):
        if state["verifier"] is not None:  # signed-in mode: identity comes from the token, never from the form
            user = current_user(bearer(authorization))
            # The wallet is optional here: it can be added on the profile page afterwards, which also
            # copies it into the face store (see the profile update below), so enrollment is not blocked on it.
            user_id, wallet = user["user_id"], user["sol_wallet"] or ""
        elif state["accounts"] is not None:  # production (Databricks accounts on) but login not configured: never enroll anonymously
            raise HTTPException(503, "Login is not configured (set AUTH0_DOMAIN and AUTH0_AUDIENCE), so enrollment is closed.")
        elif not user_id or not wallet:
            raise HTTPException(400, "user_id and wallet are required.")
        if not consent:
            raise HTTPException(400, "Consent is required to store a face embedding.")
        if not USER_ID_RE.match(user_id):
            raise HTTPException(400, "user_id must be 1-64 letters, digits, '.', '_' or '-'.")
        wallet = wallet.strip()
        if wallet and not SOLANA_ADDR_RE.match(wallet):
            raise HTTPException(400, "That does not look like a Solana wallet address.")
        if state["store"].user_exists(user_id):
            raise HTTPException(409, "User already enrolled. Delete first to re-enroll.")
        if not config.MIN_ENROLL_FRAMES <= len(frames) <= config.MAX_ENROLL_FRAMES:
            raise HTTPException(400, f"Send {config.MIN_ENROLL_FRAMES}-{config.MAX_ENROLL_FRAMES} frames.")

        wanted = [p.strip() for p in poses.split(",") if p.strip()]
        if wanted and (len(wanted) != len(frames) or any(p not in POSE_HINTS for p in wanted)):
            raise HTTPException(400, "poses must list front, left or right once per frame.")
        embeddings, problems = [], []
        for i, f in enumerate(frames):
            try:
                face = pick_face(get_engine().analyse(decode_image(await f.read())))
                check_quality(face)  # strict tier: bad frames must not become templates
                if wanted and enroll_pose(face.turn) != wanted[i]:  # the photo must really show the asked direction
                    raise QualityError(f"Expected your head turned {'straight' if wanted[i] == 'front' else 'to your ' + wanted[i]}, "
                                       f"but the photo shows a different direction.")
                embeddings.append(face.embedding)
            except QualityError as e:
                problems.append(f"frame {i + 1}: {e}")
        if len(embeddings) < config.MIN_ENROLL_FRAMES:
            raise HTTPException(422, {"message": "Not enough usable frames.", "problems": problems})

        # One face, one account: a face that already matches somebody else is refused, otherwise two accounts would hold the
        # same face (bin lookups become ambiguous, and one person could collect rewards under several wallets).
        # The person may choose to REPLACE the old account (replace=true): their old face data and profile are deleted and this
        # account becomes the main one. Only allowed when every photo clearly matches exactly one old account.
        owners, gallery = state["store"].all_embeddings()
        clash: dict[str, list[float]] = {}
        if len(owners):
            for emb in embeddings:
                sims = gallery @ emb
                best = int(np.argmax(sims))
                if float(sims[best]) >= config.MATCH_THRESHOLD and owners[best] != user_id:
                    clash.setdefault(owners[best], []).append(float(sims[best]))
        replaced = False
        if clash:
            if not replace:
                raise HTTPException(409, {"message": "This face is already registered to another account.", "code": "face_already_registered"})
            old = next(iter(clash))
            if len(clash) != 1 or len(clash[old]) != len(embeddings):
                raise HTTPException(409, {"message": "These photos do not clearly match one single account, so the old one cannot be replaced automatically.",
                                          "code": "face_replace_refused"})
            if float(np.mean(clash[old])) < config.REPLACE_MIN_SIMILARITY:
                raise HTTPException(409, {"message": "The match with the old account is not strong enough to replace it. Try again facing the camera in good light.",
                                          "code": "face_replace_refused"})
            log.warning("face replace old_user=%s new_user=%s mean_similarity=%.3f frames=%d", old, user_id, float(np.mean(clash[old])), len(embeddings))
            state["store"].delete_user(old)
            state["sessions"].close_user(old)
            if state["accounts"] is not None:
                state["accounts"].delete_profile(old)
            replaced = True
        state["store"].add_user(user_id, wallet, embeddings)
        if state["accounts"] is not None:
            state["accounts"].forget(user_id)
        return {"enrolled": True, "user_id": user_id, "frames_used": len(embeddings), "problems": problems, "replaced_old_account": replaced}

    @app.post("/pose")
    async def pose(frame: UploadFile = File(...)):
        """Which way is the head turned in this frame? Used by the enrollment page to take each photo only when the
        requested direction is really shown. Nothing is stored."""
        try:
            face = pick_face(get_engine().analyse(decode_image(await frame.read())))
        except QualityError as e:
            return {"found": False, "hint": str(e)}
        p = enroll_pose(face.turn)
        return {"found": True, "pose": p, "turn": None if face.turn is None else round(face.turn, 3),
                "hint": {"between": "Turn a little more.", "profile": "That's too far. Turn back a little."}.get(p, "")}

    @app.post("/match")
    async def match_face(frame: UploadFile = File(...), session_token: str | None = Form(None)):
        """Identify the face. With liveness on, a match returns a challenge instead of a session;
        finish it via POST /liveness/{challenge_id}/frame. Passing the current live session_token
        lets the same person refresh without a new challenge, for LIVENESS_VALID_SECONDS only."""
        try:
            face = pick_face(get_engine().analyse(decode_image(await frame.read())))
            check_quality(face, identification=True)  # lenient tier
        except QualityError as e:
            return {"matched": False, "reason": "bad_frame", "message": str(e)}
        owners, gallery = state["store"].all_embeddings()
        res = match(face.embedding, owners, gallery)
        # Scores belong in the log, not in what a user sees (no embeddings are ever logged).
        log.info("match matched=%s user=%s similarity=%.3f threshold=%.2f margin=%.2f reason=%s",
                 res.matched, res.user_id if res.matched else "-", res.score, config.MATCH_THRESHOLD, config.AMBIGUITY_MARGIN,
                 res.reason or "ok")
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
            check_quality(face, identification=True)
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
    def delete_user(user_id: str, authorization: str | None = Header(None)):
        if state["accounts"] is not None:  # production: only the signed-in owner may delete their own face data
            if state["verifier"] is None:
                raise HTTPException(503, "Login is not configured, so deletion is closed.")
            if current_user(bearer(authorization))["user_id"] != user_id:
                raise HTTPException(403, "You can only delete your own face data.")
        if not state["store"].delete_user(user_id):
            raise HTTPException(404, "No such user.")
        state["sessions"].close_user(user_id)
        if state["accounts"] is not None:
            state["accounts"].forget(user_id)
        return {"deleted": True}

    # ---- accounts (Auth0 login) -------------------------------------------------------------
    @app.get("/me")
    def me(authorization: str | None = Header(None)):
        return current_user(bearer(authorization))  # includes face_enrolled; one cached query

    @app.put("/me")
    def update_me(body: dict = Body(...), authorization: str | None = Header(None)):
        u = current_user(bearer(authorization))
        try:
            need_accounts().update_profile(u["user_id"], body.get("username"), body.get("pseudonym"), body.get("sol_wallet"))
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        wallet = body.get("sol_wallet")
        if wallet and state["store"].user_exists(u["user_id"]):  # keep the wallet the bin pays to in step with the profile
            state["store"].set_wallet(u["user_id"], wallet.strip())
        out = dict(need_accounts().user_by_sub(u["auth0_sub"]))
        if wallet and state["payouts"] is not None:  # rewards held for lack of a wallet are paid now (the cron finishes any left)
            try:
                out.update(state["payouts"].release_held(u["user_id"]))
            except Exception as e:  # the wallet is saved either way; held rows stay held and are released on the next save
                log.warning("release_held user=%s failed: %s", u["user_id"], type(e).__name__)
                out.update({"held_queued": 0, "held_paid": 0, "held_error": "Your wallet is saved, but held rewards could not be released yet."})
        return out

    @app.get("/me/activity")
    def my_activity(range: str = "week", tz: str = "", authorization: str | None = Header(None)):
        if range not in RANGES:
            raise HTTPException(400, f"range must be one of {', '.join(RANGES)}.")
        u = current_user(bearer(authorization))
        zi = zone(tz)
        start, _, _ = window(range, zi)
        rows = need_payouts().ledger.rows_for_user(u["user_id"], start)
        return summarise(rows, range, zi)

    @app.get("/rewards")
    def reward_table():
        return rewards.table()

    # ---- kids' sorting game ------------------------------------------------------------------
    @app.get("/game/leaderboard")
    def game_leaderboard(period: str = "week", limit: int = 10, authorization: str | None = Header(None)):
        from .game import PERIODS

        if period not in PERIODS:
            raise HTTPException(400, f"period must be one of {', '.join(PERIODS)}.")
        me = None
        if authorization:  # optional: only used to mark the caller's own row
            try:
                me = current_user(bearer(authorization))["user_id"]
            except HTTPException:
                me = None
        g = need_game()
        board = g.leaderboard(period, max(1, min(limit, 50)), me)
        mine = None
        if me:
            best = g.best(me, period)
            mine = {"best": best, "rank": g.rank_of(best, period) if best else None}
        return {"period": period, "leaderboard": board, "me": mine}

    @app.post("/game/scores")
    def game_score(body: dict = Body(...), authorization: str | None = Header(None)):
        from .game import TooFast, check_result

        u = current_user(bearer(authorization))
        try:
            result = check_result(body)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        try:
            return need_game().save(u["user_id"], result)
        except TooFast as e:
            raise HTTPException(429, str(e)) from e

    @app.put("/game/nickname")
    def game_nickname(body: dict = Body(...), authorization: str | None = Header(None)):
        from .game import clean_nickname

        u = current_user(bearer(authorization))
        try:
            name = clean_nickname(str(body.get("nickname", "")))
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        need_accounts().update_profile(u["user_id"], None, name, None)
        return {"nickname": name}

    @app.get("/leaderboard")
    def leaderboard(limit: int = 20):
        return {"leaderboard": need_accounts().leaderboard(max(1, min(limit, 100)))}

    # ---- bin -> server (authenticated by X-Bin-Key) ----------------------------------------
    def bin_id_of(key: str | None) -> str:
        found = bin_for_key(key)
        if not found:
            raise HTTPException(401, "Missing or invalid X-Bin-Key.")
        return found

    @app.get("/gallery")
    def gallery(response: Response, x_bin_key: str | None = Header(None), if_none_match: str | None = Header(None)):
        """Face templates for a bin that identifies people ON THE DEVICE (no network call per frame). Bin key only.
        These are biometric templates of every enrolled person: only trusted bins get them, over HTTPS. float16 keeps it small."""
        bin_id_of(x_bin_key)
        owners, mat = state["store"].all_embeddings()
        version = hashlib.sha1(mat.tobytes() + "|".join(owners).encode()).hexdigest()[:16]
        if if_none_match == version:
            return Response(status_code=304, headers={"ETag": version})
        order = list(dict.fromkeys(owners))
        people = [{"user_id": u, "embeddings_b64": base64.b64encode(mat[[i for i, o in enumerate(owners) if o == u]].astype(np.float16).tobytes()).decode()}
                  for u in order]
        response.headers["ETag"] = version
        return {"version": version, "dim": int(mat.shape[1]) if len(owners) else 512, "people": people}

    @app.post("/interactions")
    def new_interaction(body: dict = Body(...), x_bin_key: str | None = Header(None)):
        """One sorted item. `interaction_id` is chosen by the bin and makes retries safe: the same id is stored once and paid
        at most once. The user comes from the live bin session (face already checked), so no face data is sent or kept per item.
        The reward is decided here from the item class (app/rewards.py); any amount the bin sends is ignored."""
        bin_id = bin_id_of(x_bin_key)
        iid, item = str(body.get("interaction_id", "")).strip(), str(body.get("item_class", "")).strip().lower()
        if not iid or not item:
            raise HTTPException(400, "interaction_id and item_class are required.")
        if len(iid) > 128:
            raise HTTPException(400, "interaction_id is too long.")
        token = body.get("session_token")
        user_id = state["sessions"].user_for(str(token)) if token else None
        claimed = str(body.get("user_id") or "").strip()   # a bin that identifies people itself (local identity) names them; the bin key vouches for it
        if user_id is None and claimed and state["store"].user_exists(claimed):
            user_id = claimed
        row, created = need_payouts().record(iid, bin_id, item, body.get("confidence"), user_id,
                                            state["sessions"].session_id(str(token)) if token else None)
        return {**public(row), "duplicate": not created}

    def check_cron(authorization: str | None):
        if not config.CRON_SECRET:
            raise HTTPException(503, "CRON_SECRET is not set.")
        if not authorization or not secrets.compare_digest(authorization.encode(), f"Bearer {config.CRON_SECRET}".encode()):
            raise HTTPException(401, "Bad cron secret.")

    @app.get("/cron/reconcile")
    def reconcile(authorization: str | None = Header(None)):
        """Vercel cron (vercel.json, every minute). Safe to overlap with itself and with live requests."""
        check_cron(authorization)
        return need_payouts().reconcile()

    return app


def app_factory() -> FastAPI:
    return create_app()
