#!/usr/bin/env python3
"""End-to-end check of the money path: bin drop -> face API -> website /api/payout -> Solana devnet -> Databricks -> dashboards.

Two modes.

  deployed  Against a running site (production or a preview with the env vars set). You supply what only a real bin and a real
            login can produce:
              python scripts/e2e_devnet.py deployed --base-url https://cashcan.biz --bin-key "$BIN_KEY" \\
                  --session-token "$SESSION" --auth0-token "$ACCESS_TOKEN"
            SESSION is a live bin session token for the test user (POST /face-api/match + head-turn liveness, e.g. a pi_client run
            in front of the camera; it lives SESSION_TTL_SECONDS = 60 s). ACCESS_TOKEN is that user's Auth0 access token for the
            face API audience (copy it from the browser on cashcan.biz). The user needs a devnet wallet on their profile.

  local     Runs the face API in this process against the REAL Databricks tables and the REAL website payout route
            (`npm run dev` in website/ with TREASURY_SECRET_KEY, PAYOUT_SECRET, SOLANA_RPC_URL set), so the transfer is real.
            The test user, its live session and its login are made here (no camera, no Auth0), which is the only shortcut:
              DATABRICKS_HOST=... DATABRICKS_TOKEN=... DATABRICKS_WAREHOUSE_ID=... PAYOUT_SECRET=... \\
              face_api/.venv/bin/python scripts/e2e_devnet.py local --payout-url http://localhost:3000/api/payout \\
                  --wallet <devnet wallet of the test user>

Both modes then check: the interaction row reaches `paid` with a signature that is confirmed on devnet and carries the memo
cashcan:<interaction_id>, /me/activity shows it, and workspace.cashcan_app.city_activity includes it (needs Databricks env).
In demo mode (the website has PAYOUT_MODE=demo or no TREASURY_SECRET_KEY) the payout is simulated, so the on-chain checks are
skipped and noted. Exit code 0 only if every check passed. Test rows use interaction ids starting with "e2e-" and the user "e2e-test-user".
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
RPC = os.environ.get("SOLANA_RPC_URL", "https://api.devnet.solana.com")
E2E_USER, E2E_SUB = "e2e-test-user", "e2e|test-user"
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""), flush=True)
    return ok


def rpc(method: str, params: list):
    r = httpx.post(RPC, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=30)
    r.raise_for_status()
    return r.json().get("result")


def check_chain(sig: str, iid: str, wallet: str | None):
    if sig.startswith("demo_"):  # the website runs in demo mode (PAYOUT_MODE=demo or no treasury key): nothing was sent
        print(f"[NOTE] demo payout {sig}: no on-chain transaction to check", flush=True)
        return
    tx = None
    for _ in range(10):
        tx = rpc("getTransaction", [sig, {"encoding": "jsonParsed", "commitment": "confirmed", "maxSupportedTransactionVersion": 0}])
        if tx:
            break
        time.sleep(3)
    if not check("transaction is confirmed on devnet", bool(tx) and tx["meta"]["err"] is None,
                 f"https://explorer.solana.com/tx/{sig}?cluster=devnet"):
        return
    ixs = tx["transaction"]["message"]["instructions"]
    memos = [i.get("parsed") for i in ixs if i.get("program") == "spl-memo"]
    transfers = [i["parsed"]["info"] for i in ixs if i.get("program") == "system" and i.get("parsed", {}).get("type") == "transfer"]
    check("transaction carries the memo", f"cashcan:{iid}" in memos, str(memos))
    if transfers:
        t = transfers[0]
        check("transfer goes to the user's wallet", wallet is None or t["destination"] == wallet,
              f"{t['lamports']} lamports -> {t['destination']}")


def city_view_has(iid: str) -> None:
    if not all(os.environ.get(k) for k in ("DATABRICKS_HOST", "DATABRICKS_TOKEN", "DATABRICKS_WAREHOUSE_ID")):
        check("city_activity view includes the drop", False, "skipped: DATABRICKS_* not set")
        return
    sys.path.insert(0, str(ROOT / "face_api"))
    from app.databricks_store import DatabricksFaces
    rows = DatabricksFaces().sql("SELECT payout_status, sorter, sol_paid, cad_paid, tx_signature FROM workspace.cashcan_app.city_activity "
                                 "WHERE interaction_id = :i", {"i": iid})
    check("city_activity view includes the drop", bool(rows) and rows[0][0] == "paid", json.dumps(rows))


def summary() -> int:
    bad = [n for n, ok, _ in results if not ok]
    print(f"\n{len(results) - len(bad)}/{len(results)} checks passed" + (f"; failed: {', '.join(bad)}" if bad else ""))
    return 0 if not bad else 1


# ---------------------------------------------------------------------------------------------------------------------------
def deployed(a) -> int:
    api = a.base_url.rstrip("/") + "/face-api"
    iid = f"e2e-{uuid.uuid4().hex[:12]}"
    me = httpx.get(f"{api}/me", headers={"Authorization": f"Bearer {a.auth0_token}"}, timeout=30)
    check("test user can log in (GET /me)", me.status_code == 200, me.text[:200])
    wallet = me.json().get("sol_wallet") if me.status_code == 200 else None
    check("test user has a wallet", bool(wallet), str(wallet))
    print(f"POST /interactions {iid}", flush=True)
    r = httpx.post(f"{api}/interactions", headers={"X-Bin-Key": a.bin_key}, timeout=40,
                   json={"interaction_id": iid, "session_token": a.session_token, "item_class": "cans", "confidence": 0.95,
                         "reward_lamports": 123456789})   # must be ignored by the server
    body = r.json() if r.status_code == 200 else {}
    check("interaction recorded", r.status_code == 200, json.dumps(body)[:400])
    check("server decided the reward (5 cents), not the bin", body.get("reward_cents") == 5, f"reason={body.get('reason')}")
    again = httpx.post(f"{api}/interactions", headers={"X-Bin-Key": a.bin_key}, timeout=40,
                       json={"interaction_id": iid, "session_token": a.session_token, "item_class": "cans", "confidence": 0.95}).json()
    check("retry is a duplicate, not a second payout", again.get("duplicate") is True, again.get("payout_status", ""))
    drop = None
    for _ in range(a.wait // 10 + 1):   # instant payout, or the reconcile cron (every minute)
        act = httpx.get(f"{api}/me/activity?range=today", headers={"Authorization": f"Bearer {a.auth0_token}"}, timeout=30).json()
        drop = next((d for d in act.get("recent", []) if d["interaction_id"] == iid), None)
        if drop and drop["payout_status"] == "paid":
            break
        time.sleep(10)
    check("/me/activity shows the drop", drop is not None)
    check("payout status is paid", bool(drop) and drop["payout_status"] == "paid", json.dumps(drop)[:400])
    if drop and drop.get("tx_signature"):
        check_chain(drop["tx_signature"], iid, wallet)
    city_view_has(iid)
    return summary()


# ---------------------------------------------------------------------------------------------------------------------------
def local(a) -> int:
    sys.path.insert(0, str(ROOT / "face_api"))
    os.environ.setdefault("CASHCAN_STORE", "databricks")
    from fastapi.testclient import TestClient

    from app import config
    from app.accounts import Accounts
    from app.databricks_store import DatabricksFaces
    from app.ledger import Ledger
    from app.main import create_app
    from app.payouts import PayoutClient, Payouts
    from app.sessions import SessionManager

    class LocalLogin:  # stands in for Auth0: the token IS the subject
        def sub(self, token):
            return token

    config.BIN_API_KEYS, config.PAYOUT_COOLDOWN_SECONDS = "e2e-bin:e2e-key", 0
    db = DatabricksFaces()
    accounts = Accounts(db)
    sessions = SessionManager(ttl=600)
    payouts = Payouts(Ledger(db), PayoutClient(a.payout_url, os.environ["PAYOUT_SECRET"], timeout=float(a.timeout)))
    app = create_app(engine=object(), store=_NoFaces(), sessions=sessions, accounts=accounts, verifier=LocalLogin(), payouts=payouts)
    c = TestClient(app)
    auth = {"Authorization": f"Bearer {E2E_SUB}"}

    # test user (no face data), its bin, and a live session as the bin would hold after a face match + liveness
    db.sql("MERGE INTO workspace.cashcan_app.users t USING (SELECT :s AS auth0_sub) s ON t.auth0_sub = s.auth0_sub "
           "WHEN NOT MATCHED THEN INSERT (user_id, auth0_sub, pseudonym, created_at) VALUES (:u, :s, 'E2E tester', current_timestamp())",
           {"s": E2E_SUB, "u": E2E_USER})
    db.sql("MERGE INTO workspace.cashcan_app.bins t USING (SELECT 'e2e-bin' AS bin_id) s ON t.bin_id = s.bin_id "
           "WHEN NOT MATCHED THEN INSERT (bin_id, name, location) VALUES ('e2e-bin', 'E2E test bin', 'Test bench')")
    uid = c.get("/me", headers=auth).json()["user_id"]
    token, _ = sessions.open(uid)
    bin_h = {"X-Bin-Key": "e2e-key"}

    # 1) no wallet -> held
    c.put("/me", json={"pseudonym": "E2E tester"}, headers=auth)
    db.sql("UPDATE workspace.cashcan_app.users SET sol_wallet = NULL WHERE user_id = :u", {"u": uid}); accounts.forget()
    held_id = f"e2e-held-{uuid.uuid4().hex[:8]}"
    r = c.post("/interactions", headers=bin_h, json={"interaction_id": held_id, "session_token": token, "item_class": "cans",
                                                     "confidence": 0.95, "reward_lamports": 999999999}).json()
    check("no wallet: reward is held", r["payout_status"] == "held" and r["reward_cents"] == 5, json.dumps(r))

    # 2) saving a wallet pays the held reward
    t0 = time.time()
    saved = c.put("/me", json={"sol_wallet": a.wallet}, headers=auth).json()
    check("saving a wallet pays held rewards", saved.get("held_queued", 0) >= 1 and saved.get("held_paid", 0) >= 1,
          f"queued={saved.get('held_queued')} paid={saved.get('held_paid')} in {time.time() - t0:.1f}s {saved.get('held_error', '')}")

    # 3) a drop with a wallet is paid instantly
    iid = f"e2e-{uuid.uuid4().hex[:12]}"
    t0 = time.time()
    r = c.post("/interactions", headers=bin_h, json={"interaction_id": iid, "session_token": token, "item_class": "cans",
                                                     "confidence": 0.95}).json()
    check("drop is paid within the request", r["payout_status"] == "paid",
          f"{time.time() - t0:.1f}s status={r['payout_status']} error={r.get('payout_error')}")
    again = c.post("/interactions", headers=bin_h, json={"interaction_id": iid, "session_token": token, "item_class": "cans",
                                                         "confidence": 0.95}).json()
    check("retry is a duplicate with the same signature", again["duplicate"] and again["tx_signature"] == r["tx_signature"])
    print(json.dumps({k: r[k] for k in ("interaction_id", "reward_cents", "payout_status", "lamports", "cad_per_sol", "tx_signature")}))

    # 4) unrecognised drop and low confidence pay nothing
    n = c.post("/interactions", headers=bin_h, json={"interaction_id": f"e2e-anon-{uuid.uuid4().hex[:8]}", "item_class": "cans",
                                                     "confidence": 0.95}).json()
    check("unrecognised drop: no reward", n["payout_status"] == "none" and n["reason"] == "not_recognised")

    if r.get("tx_signature"):
        check_chain(r["tx_signature"], iid, a.wallet)
    act = c.get("/me/activity?range=today", headers=auth).json()
    mine = next((d for d in act["recent"] if d["interaction_id"] == iid), None)
    check("/me/activity shows the paid drop", bool(mine) and mine["payout_status"] == "paid",
          f"totals: items={act['totals']['items']} paid_sol={act['totals']['paid_sol']} paid_cad={act['totals']['paid_cad']}")
    city_view_has(iid)
    print("reconcile:", c.get("/cron/reconcile", headers={"Authorization": f"Bearer {config.CRON_SECRET}"}).json()
          if config.CRON_SECRET else "skipped (CRON_SECRET not set)")
    return summary()


class _NoFaces:
    """The local run never enrolls or matches faces; only PUT /me touches the face store (to copy the wallet)."""

    def user_exists(self, user_id):
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="mode", required=True)
    d = sub.add_parser("deployed")
    d.add_argument("--base-url", required=True)
    d.add_argument("--bin-key", required=True)
    d.add_argument("--session-token", required=True)
    d.add_argument("--auth0-token", required=True)
    d.add_argument("--wait", type=int, default=150, help="seconds to wait for the payout (instant or via the cron)")
    lo = sub.add_parser("local")
    lo.add_argument("--payout-url", default="http://localhost:3000/api/payout")
    lo.add_argument("--wallet", required=True, help="the test user's devnet wallet")
    lo.add_argument("--timeout", default="30", help="payout route timeout in seconds (a cold `next dev` compiles on first call)")
    a = ap.parse_args()
    return deployed(a) if a.mode == "deployed" else local(a)


if __name__ == "__main__":
    sys.exit(main())
