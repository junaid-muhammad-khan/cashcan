"""Rewards, interaction status transitions, idempotency, cooldown, held rewards, the reconcile job and /me/activity."""
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import config, rewards
from app.accounts import Accounts
from app.activity import summarise, zone
from app.auth import TokenVerifier
from app.main import create_app
from app.payouts import PayoutClient, Payouts, drop_reward
from app.sessions import SessionManager
from app.store import FaceStore
from tests.conftest import FakeEngine, WALLET
from tests.fakes import FakePayoutClient, MemoryLedger
from tests.test_accounts_api import AUD, DOMAIN, FakeDB, Resolver, auth

BIN = {"X-Bin-Key": "secretkey"}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "BIN_API_KEYS", "bin-1:secretkey")
    monkeypatch.setattr(config, "REQUIRE_LIVENESS", False)
    monkeypatch.setattr(config, "CRON_SECRET", "cron-s3cret")
    db, sessions = FakeDB(), SessionManager()
    wallet_of = lambda uid: next((u.get("sol_wallet") for u in db.users.values() if u["user_id"] == uid), None)
    ledger, client = MemoryLedger(wallet_of), FakePayoutClient()
    payouts = Payouts(ledger, client)
    app = create_app(engine=FakeEngine(), store=FaceStore(str(tmp_path / "f.db")), sessions=sessions, accounts=Accounts(db),
                     verifier=TokenVerifier(DOMAIN, AUD, key_resolver=Resolver()), payouts=payouts)

    class E:
        pass
    e = E()
    e.c, e.db, e.sessions, e.ledger, e.client, e.payouts = TestClient(app), db, sessions, ledger, client, payouts

    def user(wallet=True, sub="auth0|abc"):
        uid = e.c.get("/me", headers=auth(sub=sub)).json()["user_id"]
        if wallet:
            e.c.put("/me", json={"sol_wallet": WALLET}, headers=auth(sub=sub))
        return uid, e.sessions.open(uid)[0]
    e.user = user
    e.drop = lambda iid, tok=None, item="cans", conf=0.93, **kw: e.c.post(
        "/interactions", json={"interaction_id": iid, "session_token": tok, "item_class": item, "confidence": conf, **kw}, headers=BIN)
    return e


# ---- reward table ---------------------------------------------------------------------------
def test_reward_table_is_half_the_bc_deposit():
    assert rewards.reward_cents("cans") == 5 and rewards.reward_cents("CANS") == 5
    assert rewards.reward_cents("organics") == 0 and rewards.reward_cents("waste") == 0 and rewards.reward_cents("glass?") == 0


def test_get_rewards(env):
    t = env.c.get("/rewards").json()
    assert t["classes"] == {"cans": 5, "organics": 0, "waste": 0} and t["deposit_cents"] == 10 and t["cash_back_share"] == 0.5


def test_website_price_list_agrees_with_the_reward_table():
    """website/lib/prices.ts is the Prices page's fallback copy: every container must pay exactly the server's 'cans' amount."""
    src = (Path(__file__).resolve().parents[2] / "website" / "lib" / "prices.ts").read_text()
    share = float(re.search(r"CASH_BACK_SHARE\s*=\s*([0-9.]+)", src).group(1))
    deposits = [int(x) for x in re.findall(r"depositCents:\s*(\d+)", src)]
    assert share == rewards.CASH_BACK_SHARE and deposits and all(d == rewards.BC_DEPOSIT_CENTS for d in deposits)
    assert all(round(d * share) == rewards.REWARD_CENTS["cans"] for d in deposits)
    other = dict(re.findall(r'id: "(organics|waste)".*?cents: (\w+)', src))
    assert other == {"organics": "0", "waste": "0"}


def test_drop_reward_gates(monkeypatch):
    monkeypatch.setattr(config, "MIN_CONFIDENCE", 0.75)
    assert drop_reward("cans", "u", 0.9) == (5, None)
    assert drop_reward("cans", None, 0.9) == (0, "not_recognised")
    assert drop_reward("cans", "u", 0.74) == (0, "low_confidence")
    assert drop_reward("cans", "u", None) == (0, "low_confidence")
    assert drop_reward("waste", "u", 0.99) == (0, "not_reward_eligible")


# ---- POST /interactions ---------------------------------------------------------------------
def test_bin_key_is_optional_unless_required(env, monkeypatch):
    from app import config

    r = env.c.post("/interactions", json={"interaction_id": "x", "item_class": "cans"})
    assert r.status_code == 200                                   # bins are allowed without a key
    monkeypatch.setattr(config, "BIN_AUTH_REQUIRED", True)
    assert env.c.post("/interactions", json={"interaction_id": "x2", "item_class": "cans"}).status_code == 401
    assert env.c.post("/interactions", json={"interaction_id": "x"}, headers=BIN).status_code == 400


def test_paying_drop_is_paid_instantly_and_ignores_the_bins_amount(env):
    uid, tok = env.user()
    r = env.drop("i-1", tok, reward_lamports=999_999_999).json()
    assert r["payout_status"] == "paid" and r["reward_cents"] == 5 and r["tx_signature"] == "sig-i-1" and r["duplicate"] is False
    assert env.client.sent == [("i-1", WALLET, 5)]                       # cents from the table, not the bin's lamports
    assert [m[1:] for m in env.ledger.moves] == [("pending", "sending"), ("sending", "paid")]
    row = env.ledger.rows["i-1"]
    assert row["reward_lamports"] == row["lamports"] == 5 * 79_000 and row["cad_per_sol"] == 126.5 and row["payout_attempts"] == 1


def test_retried_request_returns_the_same_row_and_never_pays_twice(env):
    uid, tok = env.user()
    a, b = env.drop("i-1", tok).json(), env.drop("i-1", tok).json()
    assert a["duplicate"] is False and b["duplicate"] is True and b["payout_status"] == "paid"
    assert len(env.client.sent) == 1 and len(env.ledger.rows) == 1


@pytest.mark.parametrize("kw,reason", [({"tok": None}, "not_recognised"), ({"conf": 0.5}, "low_confidence"),
                                       ({"item": "waste"}, "not_reward_eligible"), ({"item": "organics"}, "not_reward_eligible")])
def test_no_reward_cases_are_status_none(env, kw, reason):
    uid, tok = env.user()
    args = {"tok": tok, **kw}
    r = env.drop("i-x", **args).json()
    assert r["payout_status"] == "none" and r["reward_cents"] == 0 and r["reason"] == reason and env.client.sent == []


def test_unknown_session_token_pays_nothing(env):
    env.user()
    r = env.drop("i-x", "not-a-live-session").json()
    assert r["user_id"] is None and r["payout_status"] == "none"


def test_cooldown_is_server_side(env, monkeypatch):
    monkeypatch.setattr(config, "PAYOUT_COOLDOWN_SECONDS", 30)
    uid, tok = env.user()
    assert env.drop("i-1", tok).json()["payout_status"] == "paid"
    r = env.drop("i-2", tok).json()
    assert r["payout_status"] == "none" and r["reward_cents"] == 0 and r["reason"] == "cooldown"
    assert env.drop("i-3", tok, item="waste").json()["reason"] == "not_reward_eligible"   # non-paying drops are not "cooldown"
    env.ledger.rows["i-1"]["created_at"] -= timedelta(seconds=31)
    assert env.drop("i-4", tok).json()["payout_status"] == "paid"


def test_no_wallet_holds_the_reward_then_saving_a_wallet_pays_it(env, monkeypatch):
    monkeypatch.setattr(config, "PAYOUT_COOLDOWN_SECONDS", 0)
    uid, tok = env.user(wallet=False)
    assert env.drop("i-1", tok).json()["payout_status"] == "held"
    assert env.drop("i-2", tok).json()["payout_status"] == "held"
    assert env.client.sent == []
    r = env.c.put("/me", json={"sol_wallet": WALLET}, headers=auth()).json()
    assert r["held_queued"] == 2 and r["held_paid"] == 2 and r["sol_wallet"] == WALLET
    assert {x["payout_status"] for x in env.ledger.rows.values()} == {"paid"} and len(env.client.sent) == 2
    again = env.c.put("/me", json={"sol_wallet": WALLET}, headers=auth()).json()
    assert again["held_queued"] == 0 and len(env.client.sent) == 2


def test_failed_payout_is_recorded_and_retried_with_backoff(env, monkeypatch):
    monkeypatch.setattr(config, "PAYOUT_RETRY_BASE_SECONDS", 30)
    uid, tok = env.user()
    env.client.mode = "fail"
    r = env.drop("i-1", tok).json()
    assert r["payout_status"] == "failed" and "Treasury" in r["payout_error"]
    env.client.mode = "ok"
    assert env.payouts.reconcile()["skipped"] == 1                       # backoff not over yet
    env.ledger.age("i-1", 31)
    assert env.payouts.reconcile()["paid"] == 1
    assert env.ledger.rows["i-1"]["payout_status"] == "paid" and env.ledger.rows["i-1"]["payout_attempts"] == 2


def test_failed_payout_stops_after_max_attempts(env, monkeypatch):
    monkeypatch.setattr(config, "PAYOUT_MAX_ATTEMPTS", 2)
    uid, tok = env.user()
    env.client.mode = "fail"
    env.drop("i-1", tok)
    env.ledger.age("i-1", 10_000)
    env.payouts.reconcile()
    env.ledger.age("i-1", 10_000)
    env.payouts.reconcile()
    assert env.ledger.rows["i-1"]["payout_attempts"] == 2 and len(env.client.sent) == 2


def test_timeout_leaves_sending_and_reconcile_finds_the_memo(env, monkeypatch):
    monkeypatch.setattr(config, "PAYOUT_STUCK_SECONDS", 180)
    uid, tok = env.user()
    env.client.mode = "timeout"
    assert env.drop("i-1", tok).json()["payout_status"] == "sending"
    env.client.mode = "ok"
    assert env.payouts.reconcile()["skipped"] == 1                       # too recent to call stuck
    env.ledger.age("i-1", 200)
    assert env.payouts.reconcile()["resolved_paid"] == 1
    assert env.ledger.rows["i-1"]["payout_status"] == "paid" and env.ledger.rows["i-1"]["tx_signature"] == "sig-i-1"
    assert len(env.client.sent) == 1                                     # resolved by lookup, not by sending again


def test_stuck_sending_without_a_transfer_goes_back_to_pending_and_pays_once(env):
    uid, tok = env.user()
    env.client.mode = "timeout"
    env.drop("i-1", tok)
    env.client.chain.clear()                                             # nothing landed on chain
    env.client.mode = "ok"
    env.ledger.age("i-1", 500)
    assert env.payouts.reconcile()["back_to_pending"] == 1 and env.ledger.rows["i-1"]["payout_status"] == "pending"
    env.ledger.age("i-1", 60)
    assert env.payouts.reconcile()["paid"] == 1 and env.ledger.rows["i-1"]["payout_status"] == "paid"


def test_two_workers_cannot_both_claim_a_row(env):
    uid, tok = env.user(wallet=False)
    env.drop("i-1", tok)
    env.c.put("/me", json={"pseudonym": "x"}, headers=auth())          # no wallet: still held
    env.ledger.rows["i-1"]["payout_status"] = "pending"
    env.db.users["auth0|abc"]["sol_wallet"] = WALLET
    assert env.ledger.transition("i-1", "pending", "sending", attempt=True)
    assert not env.ledger.transition("i-1", "pending", "sending", attempt=True)   # the second worker loses
    assert env.payouts.pay("i-1", "pending")["payout_status"] == "sending" and env.client.sent == []


def test_reconcile_twice_in_a_row_pays_once(env):
    uid, tok = env.user()
    env.client.mode = "fail"
    env.drop("i-1", tok)
    env.client.mode = "ok"
    env.ledger.age("i-1", 10_000)
    env.payouts.reconcile(); env.payouts.reconcile()
    assert [s[0] for s in env.client.sent] == ["i-1", "i-1"]             # 1 failed + 1 successful send, never a third


def test_cron_endpoint_needs_the_secret(env):
    assert env.c.get("/cron/reconcile").status_code == 401
    assert env.c.get("/cron/reconcile", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert env.c.get("/cron/reconcile", headers={"Authorization": "Bearer cron-s3cret"}).json()["errors"] == 0


def test_payout_client_without_config_fails_cleanly():
    r = PayoutClient(url="", secret="").send("i", WALLET, 5)
    assert not r.ok and not r.timed_out and "not configured" in r.error


def test_payout_client_talks_to_the_route():
    import httpx
    seen = {}

    def handler(req):
        seen["auth"], seen["body"] = req.headers["authorization"], req.content
        if req.method == "GET":
            return httpx.Response(200, json={"found": False})
        return httpx.Response(200, json={"signature": "S", "lamports": 395000, "cad_per_sol": 126.5, "rate_source": "Coinbase"})
    c = PayoutClient("https://site/api/payout", "sec", transport=httpx.MockTransport(handler))
    r = c.send("i-1", WALLET, 5)
    assert r.ok and r.signature == "S" and r.lamports == 395000 and seen["auth"] == "Bearer sec" and b'"reward_cents":5' in seen["body"]
    assert c.lookup("i-1") is None
    bad = PayoutClient("https://site/api/payout", "sec", transport=httpx.MockTransport(
        lambda req: httpx.Response(503, json={"error": "Treasury balance too low"}))).send("i-1", WALLET, 5)
    assert not bad.ok and not bad.timed_out and bad.error == "Treasury balance too low"
    slow = PayoutClient("https://site/api/payout", "sec", transport=httpx.MockTransport(
        lambda req: (_ for _ in ()).throw(httpx.ReadTimeout("slow")))).send("i-1", WALLET, 5)
    assert slow.timed_out


# ---- GET /me/activity -----------------------------------------------------------------------
def test_activity_needs_login_and_a_valid_range(env):
    assert env.c.get("/me/activity").status_code == 401
    assert env.c.get("/me/activity?range=year", headers=auth()).status_code == 400


def test_activity_shape_and_only_your_own_drops(env, monkeypatch):
    monkeypatch.setattr(config, "PAYOUT_COOLDOWN_SECONDS", 0)
    uid, tok = env.user()
    other, otok = env.user(sub="auth0|other")
    env.drop("i-1", tok); env.drop("i-2", tok, item="organics"); env.drop("i-3", tok, conf=0.2)
    env.drop("o-1", otok)
    a = env.c.get("/me/activity?range=week&tz=America/Vancouver", headers=auth()).json()
    assert a["range"] == "week" and a["unit"] == "per day" and len(a["series"]) == 7
    assert a["totals"]["items"] == 3 and a["by_bin"] == {"cans": 2, "organics": 1, "waste": 0}
    assert a["totals"]["paid_count"] == 1 and a["totals"]["paid_lamports"] == 395_000
    assert a["totals"]["paid_cad"] == pytest.approx(395_000 / 1e9 * 126.5, abs=1e-4)
    assert {r["interaction_id"] for r in a["recent"]} == {"i-1", "i-2", "i-3"}
    paid = next(r for r in a["recent"] if r["interaction_id"] == "i-1")
    assert set(paid) >= {"item_class", "bin_id", "bin_name", "created_at", "reward_cents", "payout_status", "tx_signature"}
    assert "user_id" not in paid
    assert sum(b["cans"] + b["organics"] + b["waste"] for b in a["series"]) == 3


def test_new_user_has_an_empty_dashboard(env):
    env.user()
    a = env.c.get("/me/activity?range=today", headers=auth()).json()
    assert a["totals"]["items"] == 0 and a["recent"] == [] and len(a["series"]) == 24


def test_summarise_held_and_pending_and_buckets():
    tz = zone("UTC")
    now = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    def row(i, st, cents, hours_ago, lam=None):
        return {"interaction_id": i, "item_class": "cans", "payout_status": st, "reward_cents": cents, "lamports": lam,
                "cad_per_sol": 100.0 if lam else None, "created_at": now - timedelta(hours=hours_ago)}
    rows = [row("a", "held", 5, 1), row("b", "sending", 5, 2), row("c", "failed", 5, 3), row("d", "paid", 5, 4, 500_000),
            row("old", "paid", 5, 24 * 9, 1)]
    s = summarise(rows, "week", tz, now)
    t = s["totals"]
    assert t["items"] == 4 and t["held_cents"] == 5 and t["held_count"] == 1 and t["pending_count"] == 1 and t["failed_count"] == 1
    assert t["paid_cad"] == pytest.approx(0.05) and s["series"][-1]["cans"] == 4
    today = summarise(rows, "today", tz, now)
    assert today["series"][11]["cans"] == 1 and today["series"][8]["cans"] == 1   # 11:00 and 08:00
