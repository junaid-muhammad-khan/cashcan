"""In-memory stand-ins for the Databricks ledger and the website payout route, with the same claim semantics."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.ledger import COLS, SETTABLE, STATUSES
from app.payouts import SendResult


class MemoryLedger:
    def __init__(self, wallet_of=lambda uid: None, now=None):
        self.rows: dict[str, dict] = {}
        self._wallet_of = wallet_of
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.moves: list[tuple[str, str, str]] = []

    def insert(self, row):
        if row["interaction_id"] in self.rows:
            return False
        r = {c: None for c in COLS}
        r.update(row)
        r.update({"reward_lamports": 0, "payout_attempts": 0, "created_at": self.now(), "updated_at": self.now()})
        self.rows[row["interaction_id"]] = r
        return True

    def transition(self, iid, expected, new, *, attempt=False, paid=False, **fields):
        assert expected in STATUSES and new in STATUSES
        r = self.rows.get(iid)
        if not r or r["payout_status"] != expected:
            return False
        for k, v in fields.items():
            assert k in SETTABLE
            r[k] = v
        r["payout_status"], r["updated_at"] = new, self.now()
        if attempt:
            r["payout_attempts"] = (r["payout_attempts"] or 0) + 1
        if paid:
            r["paid_at"] = self.now()
        self.moves.append((iid, expected, new))
        return True

    def release_held(self, user_id):
        n = 0
        for r in self.rows.values():
            if r["user_id"] == user_id and r["payout_status"] == "held":
                r["payout_status"], r["updated_at"], n = "pending", self.now(), n + 1
        return n

    def get(self, iid):
        r = self.rows.get(iid)
        return (dict(r), self._wallet_of(r["user_id"]) if r["user_id"] else None) if r else None

    def drop_context(self, user_id, seconds, exclude):
        cutoff = self.now() - timedelta(seconds=seconds)
        cooling = any(r["user_id"] == user_id and (r["reward_cents"] or 0) > 0 and r["interaction_id"] != exclude
                      and r["created_at"] > cutoff for r in self.rows.values())
        return cooling, self._wallet_of(user_id)

    def pending_ids(self, user_id):
        return [r["interaction_id"] for r in sorted(self.rows.values(), key=lambda r: r["created_at"])
                if r["user_id"] == user_id and r["payout_status"] == "pending"]

    def for_reconcile(self, max_attempts, limit=20):
        out = [(dict(r), (self.now() - r["updated_at"]).total_seconds()) for r in sorted(self.rows.values(), key=lambda r: r["updated_at"])
               if r["payout_status"] in ("sending", "pending") or (r["payout_status"] == "failed" and r["payout_attempts"] < max_attempts)]
        return out[:limit]

    def rows_for_user(self, user_id, since, limit=5000):
        rows = [dict(r, bin_name="Test bin") for r in self.rows.values() if r["user_id"] == user_id and r["created_at"] >= since]
        return sorted(rows, key=lambda r: r["created_at"], reverse=True)[:limit]

    def age(self, iid, seconds):
        """Test helper: pretend the row last changed `seconds` ago."""
        self.rows[iid]["updated_at"] = self.now() - timedelta(seconds=seconds)


class FakePayoutClient:
    """Plays the website route. `mode` is ok | fail | timeout. Records every send; `chain` holds the memos that 'landed'."""

    configured = True

    def __init__(self, mode="ok"):
        self.mode, self.sent, self.chain = mode, [], {}

    def send(self, iid, to, cents):
        self.sent.append((iid, to, cents))
        if self.mode == "timeout":
            self.chain[iid] = {"found": True, "signature": f"sig-{iid}", "lamports": cents * 79_000, "cad_per_sol": 126.5}
            return SendResult(False, error="payout route timed out", timed_out=True)
        if self.mode == "fail":
            return SendResult(False, error="Treasury balance too low for this payout")
        if iid in self.chain:  # the real route finds the memo and returns the old transfer instead of sending again
            c = self.chain[iid]
            return SendResult(True, c["signature"], c["lamports"], c["cad_per_sol"], "Coinbase")
        self.chain[iid] = {"found": True, "signature": f"sig-{iid}", "lamports": cents * 79_000, "cad_per_sol": 126.5}
        return SendResult(True, f"sig-{iid}", cents * 79_000, 126.5, "Coinbase")

    def lookup(self, iid):
        return self.chain.get(iid)
