"""Recording interactions and paying their rewards.

The face API decides WHAT is owed (app/rewards.py, in cents) and keeps the state in Databricks (app/ledger.py). The website's
Node route POST /api/payout does the one thing that needs the treasury key: it converts cents to lamports at the live SOL/CAD
rate and sends the devnet transfer with the memo "cashcan:<interaction_id>". That route is itself idempotent: it looks for an
existing transfer with the same memo before sending, so a retry after a lost response never pays twice.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import httpx

from . import config, rewards

log = logging.getLogger("cashcan.payouts")


@dataclass
class SendResult:
    ok: bool
    signature: str | None = None
    lamports: int | None = None
    cad_per_sol: float | None = None
    rate_source: str | None = None
    error: str | None = None
    timed_out: bool = False      # we do not know whether it was sent: leave the row "sending" for the reconcile job


class PayoutClient:
    """Calls the website's payout route with the shared secret."""

    def __init__(self, url: str = "", secret: str = "", timeout: float | None = None, transport: httpx.BaseTransport | None = None):
        self.url, self.secret = url or config.PAYOUT_URL, secret or config.PAYOUT_SECRET
        self.timeout = config.PAYOUT_TIMEOUT_SECONDS if timeout is None else timeout
        self._transport = transport

    @property
    def configured(self) -> bool:
        return bool(self.url and self.secret)

    def _client(self, timeout: float) -> httpx.Client:
        return httpx.Client(timeout=timeout, transport=self._transport, headers={"Authorization": f"Bearer {self.secret}"})

    def send(self, interaction_id: str, to: str, reward_cents: int) -> SendResult:
        if not self.configured:
            return SendResult(False, error="Payouts are not configured (PAYOUT_URL / PAYOUT_SECRET).")
        try:
            with self._client(self.timeout) as c:
                r = c.post(self.url, json={"interaction_id": interaction_id, "to": to, "reward_cents": int(reward_cents)})
        except httpx.TimeoutException:
            return SendResult(False, error="payout route timed out", timed_out=True)
        except httpx.HTTPError as e:  # could not connect: nothing was sent, but stay safe and let the memo lookup decide
            return SendResult(False, error=f"payout route unreachable: {type(e).__name__}", timed_out=True)
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if r.status_code == 200 and body.get("signature"):
            num = lambda k, f: None if body.get(k) is None else f(body[k])
            return SendResult(True, body["signature"], num("lamports", int), num("cad_per_sol", float), body.get("rate_source"))
        return SendResult(False, error=str(body.get("error") or f"payout route returned HTTP {r.status_code}")[:500])

    def lookup(self, interaction_id: str) -> dict | None:
        """The on-chain transfer for this interaction (found by memo), or None. Raises when the lookup itself failed."""
        with self._client(20.0) as c:
            r = c.get(self.url, params={"interaction_id": interaction_id})
        r.raise_for_status()
        body = r.json()
        return body if body.get("found") else None


def drop_reward(item_class: str, user_id: str | None, confidence) -> tuple[int, str | None]:
    """(cents, reason when 0) for one drop, before the cooldown check."""
    cents = rewards.reward_cents(item_class)
    if cents <= 0:
        return 0, "not_reward_eligible"
    if not user_id:
        return 0, "not_recognised"
    try:
        conf = float(confidence)
    except (TypeError, ValueError):
        return 0, "low_confidence"
    if conf < config.MIN_CONFIDENCE:
        return 0, "low_confidence"
    return cents, None


def public(row: dict) -> dict:
    """What the bin and the website see of a row."""
    sol = None if row.get("lamports") is None else row["lamports"] / 1e9
    return {"interaction_id": row["interaction_id"], "user_id": row.get("user_id"), "item_class": row.get("item_class"),
            "reward_cents": row.get("reward_cents") or 0, "payout_status": row.get("payout_status"), "reason": row.get("reason"),
            "lamports": row.get("lamports"), "sol": sol, "cad_per_sol": row.get("cad_per_sol"),
            "tx_signature": row.get("tx_signature"), "payout_error": row.get("payout_error")}


class Payouts:
    def __init__(self, ledger, client: PayoutClient | None = None, clock=time.monotonic):
        self.ledger, self.client, self._clock = ledger, client or PayoutClient(), clock

    # ---- bin drop
    def record(self, interaction_id: str, bin_id: str, item_class: str, confidence, user_id: str | None,
               session_id: str | None) -> tuple[dict, bool]:
        """Store one drop (once) and pay it now if it is owed and a wallet is known. Returns (row, created).
        About 5 Databricks round trips on the paying path (each costs ~1 s), plus the payout route."""
        cents, reason = drop_reward(item_class, user_id, confidence)
        wallet = None
        if cents:
            cooling, wallet = self.ledger.drop_context(user_id, config.PAYOUT_COOLDOWN_SECONDS, interaction_id)
            if cooling:
                cents, reason, wallet = 0, "cooldown", None
        status = "none" if not cents else ("pending" if wallet else "held")
        row = {"interaction_id": interaction_id, "user_id": user_id, "session_id": session_id, "bin_id": bin_id,
               "item_class": item_class, "confidence": confidence, "reward_cents": cents, "payout_status": status, "reason": reason}
        if not self.ledger.insert(row):  # a retried request: the stored row, never a second payout
            return self.ledger.get(interaction_id)[0], False
        if status == "pending":
            return self.pay(interaction_id, "pending", known=(row, wallet)), True
        return row, True

    # ---- one payout
    def pay(self, interaction_id: str, expected: str, known: tuple[dict, str | None] | None = None) -> dict | None:
        """Claim the row (expected -> sending), call the payout route, store the result. Safe to call from any worker.
        `known` = (row, wallet) the caller already holds, to save a read."""
        got = known or self.ledger.get(interaction_id)
        if not got:
            return None
        row, wallet = got
        if row["payout_status"] != expected or not row.get("reward_cents"):
            return row
        if not wallet:  # no wallet on the account any more: hold it again until one is saved
            if expected == "pending":
                self.ledger.transition(interaction_id, "pending", "held")
            return self.ledger.get(interaction_id)[0]
        if not self.ledger.transition(interaction_id, expected, "sending", attempt=True, payout_wallet=wallet):
            return self.ledger.get(interaction_id)[0]  # someone else claimed it
        res = self.client.send(interaction_id, wallet, row["reward_cents"])
        if res.ok:
            self.ledger.transition(interaction_id, "sending", "paid", paid=True, tx_signature=res.signature, lamports=res.lamports,
                                   reward_lamports=res.lamports, cad_per_sol=res.cad_per_sol, rate_source=res.rate_source,
                                   payout_error=None)
            log.info("payout paid interaction=%s lamports=%s", interaction_id, res.lamports)
        elif res.timed_out:
            log.warning("payout unknown interaction=%s (%s): left as sending for the reconcile job", interaction_id, res.error)
        else:
            self.ledger.transition(interaction_id, "sending", "failed", payout_error=res.error)
            log.warning("payout failed interaction=%s: %s", interaction_id, res.error)
        return self.ledger.get(interaction_id)[0]

    # ---- held rewards
    def release_held(self, user_id: str, budget_seconds: float = 15.0) -> dict:
        """The user saved a wallet: held -> pending, then pay them one by one within the time budget (the cron pays the rest)."""
        queued = self.ledger.release_held(user_id)
        paid, start = 0, self._clock()
        if queued:
            for iid in self.ledger.pending_ids(user_id):
                if self._clock() - start > budget_seconds:
                    break
                row = self.pay(iid, "pending")
                if row and row["payout_status"] == "paid":
                    paid += 1
                elif row and row["payout_status"] == "failed" and "treasury" in (row.get("payout_error") or "").lower():
                    break  # the treasury cannot cover it: stop here, the cron retries later
        return {"held_queued": queued, "held_paid": paid}

    # ---- cron
    def reconcile(self, limit: int = 20, budget_seconds: float = 45.0) -> dict:
        """Finish what the request path could not. Safe to run twice at once: every move is a claim on the expected status."""
        out = {"paid": 0, "failed": 0, "resolved_paid": 0, "back_to_pending": 0, "skipped": 0, "errors": 0}
        start = self._clock()
        for row, age in self.ledger.for_reconcile(config.PAYOUT_MAX_ATTEMPTS, limit):
            if self._clock() - start > budget_seconds:
                break
            iid, st = row["interaction_id"], row["payout_status"]
            try:
                if st == "sending":
                    if age < config.PAYOUT_STUCK_SECONDS:
                        out["skipped"] += 1
                        continue
                    tx = self.client.lookup(iid)
                    if tx:
                        if self.ledger.transition(iid, "sending", "paid", paid=True, tx_signature=tx["signature"],
                                                  lamports=tx.get("lamports"), reward_lamports=tx.get("lamports"),
                                                  cad_per_sol=tx.get("cad_per_sol"), rate_source=tx.get("rate_source"),
                                                  payout_error=None):
                            out["resolved_paid"] += 1
                    elif self.ledger.transition(iid, "sending", "pending", payout_error="no transfer found on chain; will retry"):
                        out["back_to_pending"] += 1
                    continue
                if st == "failed":
                    wait = config.PAYOUT_RETRY_BASE_SECONDS * 2 ** max(0, (row.get("payout_attempts") or 1) - 1)
                    if age < wait:
                        out["skipped"] += 1
                        continue
                elif st == "pending" and age < 20:  # the request path is about to pay it
                    out["skipped"] += 1
                    continue
                done = self.pay(iid, st)
                key = {"paid": "paid", "failed": "failed"}.get((done or {}).get("payout_status"))
                out[key or "skipped"] += 1
            except Exception as e:  # one bad row must not stop the others
                out["errors"] += 1
                log.warning("reconcile interaction=%s: %s", iid, type(e).__name__)
        return out
