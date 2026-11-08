import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app import config
from app.accounts import Accounts
from app.auth import TokenVerifier, bin_for_key
from app.main import create_app
from app.sessions import SessionManager
from app.store import FaceStore
from tests.conftest import FakeEngine, WALLET, png

DOMAIN, AUD = "t.example.auth0.com", "https://api.cashcan"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class Resolver:
    def get_signing_key_from_jwt(self, token):
        class K: key = KEY.public_key()
        return K


def token(sub="auth0|abc", aud=AUD, iss=f"https://{DOMAIN}/", exp=3600):
    return jwt.encode({"sub": sub, "aud": aud, "iss": iss, "exp": int(time.time()) + exp}, KEY, algorithm="RS256")


class FakeDB:
    """Records SQL and plays a tiny in-memory users/interactions table."""

    schema = "workspace.cashcan_faces"

    def __init__(self):
        self.users, self.inter, self.calls = {}, {}, []

    def sql(self, stmt, params=None):
        p = params or {}
        self.calls.append((stmt, p))
        if "FROM workspace.cashcan_app.users u WHERE u.auth0_sub" in stmt:
            u = self.users.get(p["s"])
            return [[u["user_id"], p["s"], u.get("username"), u.get("pseudonym"), u.get("sol_wallet"), "false"]] if u else []
        if stmt.startswith("MERGE INTO workspace.cashcan_app.users"):
            self.users.setdefault(p["s"], {"user_id": p["id"]})
            return []
        if stmt.startswith("UPDATE workspace.cashcan_app.users"):
            col = stmt.split("SET ")[1].split(" =")[0]
            next(u for u in self.users.values() if u["user_id"] == p["u"])[col] = p["v"]
            return []
        if stmt.startswith("MERGE INTO workspace.cashcan_app.interactions"):
            new = p["i"] not in self.inter
            if new:
                self.inter[p["i"]] = {"user": p["u"], "r": int(p["r"]), "status": p["st"]}
            return [["1" if new else "0", "0", "0", "1" if new else "0"]]
        if stmt.startswith("UPDATE workspace.cashcan_app.interactions"):
            row = self.inter.get(p["i"])
            ok = bool(row) and row["status"] == "pending"
            if ok:
                row["status"] = p["st"]
            return [["1" if ok else "0"]]
        if "FROM workspace.cashcan_app.leaderboard" in stmt:
            return [["Sorter ab12", "0.5", "3"]]
        raise AssertionError(stmt)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "BIN_API_KEYS", "bin-1:secretkey")
    monkeypatch.setattr(config, "REQUIRE_LIVENESS", False)
    db, sessions = FakeDB(), SessionManager()
    store = FaceStore(str(tmp_path / "f.db"))
    app = create_app(engine=FakeEngine(), store=store, sessions=sessions,
                     accounts=Accounts(db), verifier=TokenVerifier(DOMAIN, AUD, key_resolver=Resolver()))
    client = TestClient(app)
    client.store = store
    return client, db, sessions


def auth(**kw):
    return {"Authorization": f"Bearer {token(**kw)}"}


def test_token_checks():
    v = TokenVerifier(DOMAIN, AUD, key_resolver=Resolver())
    assert v.sub(token()) == "auth0|abc"
    for bad in (token(aud="other"), token(iss="https://evil/"), token(exp=-10), "garbage"):
        with pytest.raises(Exception) as e:
            v.sub(bad)
        assert e.value.status_code == 401


def test_me_creates_once_and_needs_a_token(env):
    c, db, _ = env
    assert c.get("/me").status_code == 401
    a = c.get("/me", headers=auth()).json()
    b = c.get("/me", headers=auth()).json()
    assert a["user_id"] == b["user_id"] and len(db.users) == 1 and a["face_enrolled"] is False


def test_profile_wallet_validated(env):
    c, _, _ = env
    assert c.put("/me", json={"sol_wallet": "nope"}, headers=auth()).status_code == 400
    r = c.put("/me", json={"pseudonym": "Ace", "sol_wallet": WALLET}, headers=auth()).json()
    assert r["pseudonym"] == "Ace" and r["sol_wallet"] == WALLET


def test_enroll_takes_identity_from_token_not_form(env):
    c, _, _ = env
    files = [("frames", ("f.png", png(7), "image/png"))]
    r = c.post("/enroll", data={"consent": "true", "user_id": "someone-else", "wallet": WALLET}, files=files, headers=auth())
    assert r.status_code == 400 and "wallet" in r.text            # profile has no wallet yet
    c.put("/me", json={"sol_wallet": WALLET}, headers=auth())
    r = c.post("/enroll", data={"consent": "true", "user_id": "someone-else"}, files=files, headers=auth())
    uid = c.get("/me", headers=auth()).json()["user_id"]
    assert r.status_code == 200 and r.json()["user_id"] == uid != "someone-else"
    assert c.post("/enroll", data={"consent": "true"}, files=files).status_code == 401


def test_interaction_is_idempotent_and_payout_moves_once(env):
    c, db, sessions = env
    uid = c.get("/me", headers=auth()).json()["user_id"]
    tok, _ = sessions.open(uid)
    h = {"X-Bin-Key": "secretkey"}
    body = {"interaction_id": "i-1", "session_token": tok, "item_class": "cans", "confidence": 0.93, "reward_lamports": 5000}
    assert c.post("/interactions", json=body).status_code == 401
    assert c.post("/interactions", json=body, headers={"X-Bin-Key": "wrong"}).status_code == 401
    first = c.post("/interactions", json=body, headers=h).json()
    again = c.post("/interactions", json=body, headers=h).json()          # bin retried after a timeout
    assert first["duplicate"] is False and again["duplicate"] is True and len(db.inter) == 1
    assert db.inter["i-1"]["user"] == uid and db.inter["i-1"]["status"] == "pending"
    assert c.post("/interactions/i-1/payout", json={"status": "paid", "tx_signature": "sig"}, headers=h).json()["updated"]
    assert c.post("/interactions/i-1/payout", json={"status": "paid", "tx_signature": "sig2"}, headers=h).json()["updated"] is False
    assert c.post("/interactions/i-1/payout", json={"status": "weird"}, headers=h).status_code == 400


def test_unmatched_item_keeps_no_identity_and_no_payout(env):
    c, db, _ = env
    r = c.post("/interactions", json={"interaction_id": "i-2", "item_class": "waste", "reward_lamports": 5000},
               headers={"X-Bin-Key": "secretkey"}).json()
    assert r["user_id"] is None and db.inter["i-2"] == {"user": None, "r": 5000, "status": "none"}


def test_leaderboard_and_bin_keys(env):
    c, _, _ = env
    assert c.get("/leaderboard").json()["leaderboard"] == [{"rank": 1, "name": "Sorter ab12", "sol_earned": 0.5, "items": 3}]
    assert bin_for_key("secretkey", "bin-1:secretkey,bin-2:k2") == "bin-1" and bin_for_key("k2", "bin-1:secretkey,bin-2:k2") == "bin-2"
    assert bin_for_key(None, "bin-1:secretkey") is None and bin_for_key("x", "") is None


def test_changing_wallet_also_updates_the_wallet_the_bin_pays_to(env):
    c, _, _ = env
    other = "7EcDhSYGxXyscszYEp35KHN8vvw3svAuLKTzXwCFLtV"
    c.put("/me", json={"sol_wallet": WALLET}, headers=auth())
    c.post("/enroll", data={"consent": "true"}, files=[("frames", ("f.png", png(7), "image/png"))], headers=auth())
    uid = c.get("/me", headers=auth()).json()["user_id"]
    assert c.store.wallet(uid) == WALLET
    c.put("/me", json={"sol_wallet": other}, headers=auth())
    assert c.store.wallet(uid) == other


def test_production_mode_never_enrolls_or_deletes_anonymously(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "REQUIRE_LIVENESS", False)
    store = FaceStore(str(tmp_path / "f.db"))
    store.add_user("victim", WALLET, [__import__("numpy").ones(512, "float32") / 22.6])
    c = TestClient(create_app(engine=FakeEngine(), store=store, accounts=Accounts(FakeDB()), verifier=None))  # accounts on, Auth0 off
    files = [("frames", ("f.png", png(7), "image/png"))]
    assert c.post("/enroll", data={"consent": "true", "user_id": "x", "wallet": WALLET}, files=files).status_code == 503
    assert c.delete("/users/victim").status_code == 503 and store.user_exists("victim")


def test_delete_only_your_own_face(env):
    c, _, _ = env
    c.put("/me", json={"sol_wallet": WALLET}, headers=auth())
    c.post("/enroll", data={"consent": "true"}, files=[("frames", ("f.png", png(7), "image/png"))], headers=auth())
    uid = c.get("/me", headers=auth()).json()["user_id"]
    assert c.delete(f"/users/{uid}").status_code == 401                              # no token
    assert c.delete(f"/users/{uid}", headers=auth(sub="auth0|someone-else")).status_code == 403
    assert c.delete(f"/users/{uid}", headers=auth()).json() == {"deleted": True}


def test_returning_user_costs_one_cached_query_and_writes_forget_it(env):
    c, db, _ = env
    c.get("/me", headers=auth())                     # first login: lookup + create + lookup
    n = len(db.calls)
    c.get("/me", headers=auth()); c.get("/me", headers=auth())
    assert len(db.calls) == n                        # served from the 20 s cache: zero queries
    c.put("/me", json={"pseudonym": "Ace"}, headers=auth())
    assert c.get("/me", headers=auth()).json()["pseudonym"] == "Ace"   # not the stale cached profile
    assert len(db.calls) > n                         # the write forgot the cache, so it re-read


def test_warm_loads_the_engine(env):
    c, _, _ = env
    assert c.get("/warm").json() == {"warm": True}
