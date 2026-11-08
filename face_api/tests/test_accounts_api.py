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
        if stmt.startswith("DELETE FROM workspace.cashcan_app.users"):
            for sub in [k for k, u in self.users.items() if u["user_id"] == p["u"]]:
                del self.users[sub]
            return []
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
    from app.payouts import Payouts
    from tests.fakes import FakePayoutClient, MemoryLedger
    app = create_app(engine=FakeEngine(), store=store, sessions=sessions,
                     accounts=Accounts(db), verifier=TokenVerifier(DOMAIN, AUD, key_resolver=Resolver()),
                     payouts=Payouts(MemoryLedger(), FakePayoutClient()))
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
    # signed in, no wallet yet: allowed (the wallet is added on the profile page afterwards); identity comes from the token, not the form
    r = c.post("/enroll", data={"consent": "true", "user_id": "someone-else", "wallet": WALLET}, files=files, headers=auth())
    uid = c.get("/me", headers=auth()).json()["user_id"]
    assert r.status_code == 200 and r.json()["user_id"] == uid != "someone-else"
    assert c.store.wallet(uid) == ""                      # the form's wallet was ignored too
    c.put("/me", json={"sol_wallet": WALLET}, headers=auth())
    assert c.store.wallet(uid) == WALLET                  # saving the wallet later copies it to the face store
    assert c.post("/enroll", data={"consent": "true"}, files=files).status_code == 401


def test_bins_can_no_longer_report_their_own_payouts(env):
    """The server pays now (app/payouts.py); a bin claiming 'paid' with a signature of its choice is not an endpoint any more."""
    c, _, _ = env
    r = c.post("/interactions/i-1/payout", json={"status": "paid", "tx_signature": "sig"}, headers={"X-Bin-Key": "secretkey"})
    assert r.status_code in (404, 405)


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


def test_replacing_an_old_account_also_deletes_its_profile(env):
    c, db, _ = env
    other_sub = "auth0|second"
    files = [("frames", ("f.png", png(7), "image/png"))]
    c.put("/me", json={"sol_wallet": WALLET}, headers=auth())
    c.post("/enroll", data={"consent": "true"}, files=files, headers=auth())
    old_id = c.get("/me", headers=auth()).json()["user_id"]
    c.get("/me", headers=auth(sub=other_sub)); c.put("/me", json={"sol_wallet": WALLET}, headers=auth(sub=other_sub))
    r = c.post("/enroll", data={"consent": "true"}, files=files, headers=auth(sub=other_sub))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "face_already_registered"
    ok = c.post("/enroll", data={"consent": "true", "replace": "true"}, files=files, headers=auth(sub=other_sub))
    assert ok.status_code == 200 and ok.json()["replaced_old_account"] is True
    assert "auth0|abc" not in db.users and old_id not in [u["user_id"] for u in db.users.values()]    # the old profile row is gone
    assert not c.store.user_exists(old_id)                                                                # and its face data


def test_gallery_is_bin_only_cacheable_and_decodes_to_the_templates(env):
    import base64
    import numpy as np
    c, _, _ = env
    c.put("/me", json={"sol_wallet": WALLET}, headers=auth())
    c.post("/enroll", data={"consent": "true"}, files=[("frames", ("f.png", png(7), "image/png")), ("frames", ("f.png", png(7), "image/png"))], headers=auth())
    assert c.get("/gallery").status_code == 401 and c.get("/gallery", headers={"X-Bin-Key": "wrong"}).status_code == 401
    r = c.get("/gallery", headers={"X-Bin-Key": "secretkey"})
    g = r.json()
    uid = c.get("/me", headers=auth()).json()["user_id"]
    assert r.status_code == 200 and g["dim"] == 512 and [p["user_id"] for p in g["people"]] == [uid]
    mat = np.frombuffer(base64.b64decode(g["people"][0]["embeddings_b64"]), np.float16).reshape(-1, 512).astype(np.float32)
    assert mat.shape == (2, 512) and np.allclose(np.linalg.norm(mat, axis=1), 1, atol=5e-3)
    assert c.get("/gallery", headers={"X-Bin-Key": "secretkey", "If-None-Match": g["version"]}).status_code == 304   # unchanged: nothing resent


def test_interaction_can_name_the_user_when_the_bin_identified_them_locally(env):
    c, db, _ = env
    c.put("/me", json={"sol_wallet": WALLET}, headers=auth())
    c.post("/enroll", data={"consent": "true"}, files=[("frames", ("f.png", png(7), "image/png"))], headers=auth())
    uid = c.get("/me", headers=auth()).json()["user_id"]
    h = {"X-Bin-Key": "secretkey"}
    ok = c.post("/interactions", json={"interaction_id": "L-1", "user_id": uid, "item_class": "cans", "confidence": 0.9}, headers=h).json()
    assert ok["user_id"] == uid and ok["reward_cents"] == 5 and ok["payout_status"] in ("held", "paid")   # recognised: a reward is owed
    ghost = c.post("/interactions", json={"interaction_id": "L-2", "user_id": "not-a-user", "item_class": "cans", "confidence": 0.9}, headers=h).json()
    assert ghost["user_id"] is None and ghost["payout_status"] == "none" and ghost["reason"] == "not_recognised"   # an unknown user id is not trusted
