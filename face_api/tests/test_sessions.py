"""Signed bin session tokens: any instance with the same SESSION_SECRET accepts them; tampered, foreign or expired ones are refused."""
import json

from fastapi.testclient import TestClient

from app import config
from app.main import create_app
from app.payouts import Payouts
from app.sessions import SessionManager, _b64, _unb64
from app.store import FaceStore
from tests.conftest import FakeEngine, png
from tests.fakes import FakePayoutClient, MemoryLedger


def mgr(secret="shared-secret", t=None, ttl=60):
    t = t if t is not None else {"now": 1_000.0}
    return SessionManager(ttl=ttl, clock=lambda: t["now"], secret=secret), t


def test_token_from_one_instance_is_accepted_by_another():
    a, t = mgr()
    b, _ = mgr(t=t)                         # a different instance: no shared memory, same secret
    tok, ttl = a.open("alice")
    assert ttl == 60 and tok.startswith("s1.")
    assert b.user_for(tok) == "alice" and b.live_age(tok) == ("alice", 0.0) and b.session_id(tok) == a.session_id(tok)


def test_expiry_and_liveness_age():
    a, t = mgr()
    tok, _ = a.open("alice", live_at=990.0)
    t["now"] = 1_030.0
    assert a.live_age(tok) == ("alice", 40.0) and a.live_at(tok) == 990.0
    t["now"] = 1_060.5
    assert a.user_for(tok) is None and a.live_age(tok) is None


def test_tampered_foreign_and_garbage_tokens_are_refused():
    a, _ = mgr()
    tok, _ = a.open("alice")
    prefix, payload, sig = tok.split(".")
    claims = json.loads(_unb64(payload))
    forged = _b64(json.dumps({**claims, "u": "mallory"}).encode())
    assert a.user_for(f"{prefix}.{forged}.{sig}") is None                 # changed user, old signature
    longer = _b64(json.dumps({**claims, "e": claims["e"] + 3600}).encode())
    assert a.user_for(f"{prefix}.{longer}.{sig}") is None                 # extended expiry
    other, _ = mgr(secret="another-secret")
    assert other.user_for(tok) is None                                    # signed with a different secret
    for junk in (None, "", "abc", "s1.x.y", "s2." + payload + "." + sig, "s1." + payload, "a" * 5000, 42):
        assert a.user_for(junk) is None


def test_close_user_revokes_older_tokens_on_this_instance():
    a, t = mgr()
    old, _ = a.open("alice")
    t["now"] += 1
    a.close_user("alice")
    assert a.user_for(old) is None
    t["now"] += 1
    new, _ = a.open("alice")
    assert a.user_for(new) == "alice"                                     # a session opened after the revocation is fine


def test_without_a_secret_tokens_only_work_where_they_were_issued(monkeypatch):
    monkeypatch.setattr(config, "SESSION_SECRET", "")
    a, b = SessionManager(), SessionManager()
    tok, _ = a.open("alice")
    assert a.user_for(tok) == "alice" and b.user_for(tok) is None


def test_match_on_one_instance_and_drop_on_another_credits_the_user(tmp_path, monkeypatch):
    """The production bug this fixes: /match and /interactions reaching different serverless instances."""
    monkeypatch.setattr(config, "REQUIRE_LIVENESS", False)
    monkeypatch.setattr(config, "BIN_API_KEYS", "bin-1:k")
    store_path = str(tmp_path / "f.db")                                   # stands in for the shared Databricks store
    FaceStore(store_path).add_user("alice", "", [FakeEngine().analyse(__import__("cv2").imdecode(
        __import__("numpy").frombuffer(png(7), "uint8"), 1))[0].embedding])

    def instance():
        ledger = MemoryLedger(wallet_of=lambda uid: None)
        return TestClient(create_app(engine=FakeEngine(), store=FaceStore(store_path), sessions=SessionManager(secret="shared"),
                                     payouts=Payouts(ledger, FakePayoutClient()))), ledger
    a, _ = instance()
    b, ledger_b = instance()
    m = a.post("/match", files={"frame": ("f.png", png(7), "image/png")}).json()
    assert m["matched"] and m["user_id"] == "alice"
    r = b.post("/interactions", headers={"X-Bin-Key": "k"},
               json={"interaction_id": "x-1", "session_token": m["session_token"], "item_class": "cans", "confidence": 0.9}).json()
    assert r["user_id"] == "alice" and r["reward_cents"] == 5 and r["payout_status"] == "held"   # recognised (no wallet yet)
    assert ledger_b.rows["x-1"]["session_id"] and len(ledger_b.rows["x-1"]["session_id"]) == 8  # a random id, not the token
    assert b.get(f"/session/{m['session_token']}").json()["user_id"] == "alice"


def _open_bin_app(tmp_path, monkeypatch, required=False):
    monkeypatch.setattr(config, "REQUIRE_LIVENESS", False)
    monkeypatch.setattr(config, "BIN_API_KEYS", "bin-1:k")
    monkeypatch.setattr(config, "BIN_AUTH_REQUIRED", required)
    path = str(tmp_path / "f.db")
    FaceStore(path).add_user("alice", "", [FakeEngine().analyse(__import__("cv2").imdecode(
        __import__("numpy").frombuffer(png(7), "uint8"), 1))[0].embedding])
    ledger = MemoryLedger(wallet_of=lambda uid: None)
    app = create_app(engine=FakeEngine(), store=FaceStore(path), sessions=SessionManager(secret="shared"), payouts=Payouts(ledger, FakePayoutClient()))
    return TestClient(app), ledger


def test_a_bin_without_a_key_is_allowed_and_credits_a_live_session(tmp_path, monkeypatch):
    c, ledger = _open_bin_app(tmp_path, monkeypatch)
    m = c.post("/match", files={"frame": ("f.png", png(7), "image/png")}).json()
    r = c.post("/interactions", json={"interaction_id": "k-1", "session_token": m["session_token"], "item_class": "cans", "confidence": 0.9})
    assert r.status_code == 200 and r.json()["user_id"] == "alice" and ledger.rows["k-1"]["bin_id"] == "bin-unkeyed"


def test_an_unkeyed_bin_cannot_name_a_user_directly(tmp_path, monkeypatch):
    c, _ = _open_bin_app(tmp_path, monkeypatch)
    r = c.post("/interactions", json={"interaction_id": "k-2", "user_id": "alice", "item_class": "cans", "confidence": 0.9})
    assert r.status_code == 200 and r.json()["user_id"] is None and r.json()["reward_cents"] == 0
    keyed = c.post("/interactions", headers={"X-Bin-Key": "k"}, json={"interaction_id": "k-3", "user_id": "alice", "item_class": "cans", "confidence": 0.9})
    assert keyed.json()["user_id"] == "alice"                                   # a keyed bin still may


def test_the_gallery_of_face_templates_still_needs_a_key(tmp_path, monkeypatch):
    c, _ = _open_bin_app(tmp_path, monkeypatch)
    assert c.get("/gallery").status_code == 401


def test_bin_keys_can_be_required_again(tmp_path, monkeypatch):
    c, _ = _open_bin_app(tmp_path, monkeypatch, required=True)
    assert c.post("/interactions", json={"interaction_id": "k-4", "item_class": "cans", "confidence": 0.9}).status_code == 401
