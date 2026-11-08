"""Interactions and their payout state in Databricks (workspace.cashcan_app.interactions; columns in databricks/002_interactions_payouts.sql).

payout_status moves only along these edges, and every move is a MERGE that matches the EXPECTED current status, so two workers
(the request path, a retry, the reconcile cron) can never both claim the same row:

    none                          (no reward: nobody recognised, low confidence, non-paying class, cooldown)
    held     -> pending           (reward earned, no wallet yet; released when the user saves one)
    pending  -> sending           (claimed by exactly one worker, payout_attempts + 1)
    sending  -> paid | failed     (payout route answered)
    sending  -> pending           (reconcile: stuck, and no transaction with its memo exists on chain)
    failed   -> sending           (reconcile retry, with backoff, up to PAYOUT_MAX_ATTEMPTS sends)

Delta does not enforce keys, so interaction_id uniqueness is also a MERGE (insert when not matched): a retried bin request
inserts nothing the second time.
"""
from __future__ import annotations

from datetime import datetime, timezone

APP_SCHEMA = "workspace.cashcan_app"
STATUSES = ("none", "held", "pending", "sending", "paid", "failed")

COLS = ("interaction_id", "user_id", "session_id", "bin_id", "item_class", "confidence", "reward_cents", "reward_lamports",
        "lamports", "cad_per_sol", "rate_source", "payout_status", "payout_error", "payout_attempts", "payout_wallet",
        "tx_signature", "reason", "created_at", "updated_at", "paid_at")
INTS = {"reward_cents", "reward_lamports", "lamports", "payout_attempts"}
FLOATS = {"confidence", "cad_per_sol"}

# Fields a transition may set, with their SQL type.
SETTABLE = {"tx_signature": "STRING", "lamports": "BIGINT", "reward_lamports": "BIGINT", "cad_per_sol": "DOUBLE",
            "rate_source": "STRING", "payout_error": "STRING", "payout_wallet": "STRING"}


def parse_ts(v) -> datetime | None:
    if v is None or isinstance(v, datetime):
        return v
    s = str(v).replace("Z", "+00:00")
    if " " in s and "T" not in s:
        s = s.replace(" ", "T", 1)
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def to_row(values: list) -> dict:
    row = {}
    for k, v in zip(COLS, values):
        if v is None:
            row[k] = None
        elif k in INTS:
            row[k] = int(float(v))
        elif k in FLOATS:
            row[k] = float(v)
        elif k in ("created_at", "updated_at", "paid_at"):
            row[k] = parse_ts(v)
        else:
            row[k] = v
    return row


def _affected(rows: list) -> int:
    return int(rows[0][0]) if rows and rows[0] and rows[0][0] is not None else 0


class Ledger:
    def __init__(self, db, schema: str = APP_SCHEMA):
        self.db, self.t = db, schema

    def _select(self, alias: str = "i") -> str:
        return ", ".join(f"{alias}.{c}" for c in COLS)

    # ---- writes
    def insert(self, row: dict) -> bool:
        """Insert once (MERGE on interaction_id). False when the id already existed."""
        p = {"i": row["interaction_id"], "u": row.get("user_id"), "s": row.get("session_id"), "b": row.get("bin_id"),
             "c": row.get("item_class"), "conf": None if row.get("confidence") is None else str(float(row["confidence"])),
             "rc": str(int(row.get("reward_cents", 0))), "st": row["payout_status"], "why": row.get("reason")}
        rows = self.db.sql(
            f"MERGE INTO {self.t}.interactions t USING (SELECT :i AS interaction_id) s ON t.interaction_id = s.interaction_id "
            f"WHEN NOT MATCHED THEN INSERT (interaction_id, user_id, session_id, bin_id, item_class, confidence, reward_cents, "
            f"reward_lamports, payout_status, payout_attempts, reason, created_at, updated_at) "
            f"VALUES (:i, :u, :s, :b, :c, CAST(:conf AS DOUBLE), CAST(:rc AS INT), 0, :st, 0, :why, current_timestamp(), current_timestamp())",
            p)
        # MERGE returns [num_affected_rows, num_updated, num_deleted, num_inserted]
        return bool(rows) and int(rows[0][-1]) > 0

    def transition(self, interaction_id: str, expected: str, new: str, *, attempt: bool = False,
                   paid: bool = False, **fields) -> bool:
        """expected -> new, only if the row is still in `expected`. True when this call made the move."""
        assert expected in STATUSES and new in STATUSES
        sets, p = ["payout_status = :new", "updated_at = current_timestamp()"], {"i": interaction_id, "exp": expected, "new": new}
        for k, v in fields.items():
            typ = SETTABLE[k]  # KeyError on anything else: column names are never taken from input
            sets.append(f"{k} = CAST(:f_{k} AS {typ})")
            p[f"f_{k}"] = None if v is None else str(v)
        if attempt:
            sets.append("payout_attempts = coalesce(t.payout_attempts, 0) + 1")
        if paid:
            sets.append("paid_at = current_timestamp()")
        try:
            rows = self.db.sql(
                f"MERGE INTO {self.t}.interactions t USING (SELECT :i AS interaction_id) s ON t.interaction_id = s.interaction_id "
                f"WHEN MATCHED AND t.payout_status = :exp THEN UPDATE SET {', '.join(sets)}", p)
        except Exception as e:  # a concurrent writer won the row (Delta conflict): this call did not make the move
            if "Concurrent" in str(e) or "CONFLICT" in str(e).upper():
                return False
            raise
        return _affected(rows) > 0

    def release_held(self, user_id: str) -> int:
        """held -> pending for every held row of this user (they just saved a wallet). Returns how many moved."""
        rows = self.db.sql(
            f"MERGE INTO {self.t}.interactions t USING (SELECT :u AS user_id) s ON t.user_id = s.user_id "
            f"WHEN MATCHED AND t.payout_status = 'held' THEN UPDATE SET payout_status = 'pending', updated_at = current_timestamp()",
            {"u": user_id})
        return _affected(rows)

    # ---- reads
    def get(self, interaction_id: str) -> tuple[dict, str | None] | None:
        """(row, the user's current wallet) or None."""
        rows = self.db.sql(
            f"SELECT {self._select()}, u.sol_wallet FROM {self.t}.interactions i LEFT JOIN {self.t}.users u ON u.user_id = i.user_id "
            f"WHERE i.interaction_id = :i LIMIT 1", {"i": interaction_id})
        if not rows:
            return None
        return to_row(rows[0][:len(COLS)]), rows[0][len(COLS)]

    def drop_context(self, user_id: str, cooldown_seconds: int, exclude: str) -> tuple[bool, str | None]:
        """(paying drop by this user in the last `cooldown_seconds` other than `exclude`, the user's wallet), in ONE query.
        Server time, from the table itself."""
        rows = self.db.sql(
            f"SELECT EXISTS (SELECT 1 FROM {self.t}.interactions WHERE user_id = :u AND reward_cents > 0 AND interaction_id <> :i "
            f"AND created_at > current_timestamp() - INTERVAL {int(cooldown_seconds)} SECONDS), "
            f"(SELECT max(sol_wallet) FROM {self.t}.users WHERE user_id = :u)", {"u": user_id, "i": exclude})
        cooling, wallet = (rows[0] if rows else (False, None))
        return str(cooling).lower() == "true", wallet or None

    def pending_ids(self, user_id: str) -> list[str]:
        rows = self.db.sql(f"SELECT interaction_id FROM {self.t}.interactions WHERE user_id = :u AND payout_status = 'pending' "
                           f"ORDER BY created_at", {"u": user_id})
        return [r[0] for r in rows]

    def for_reconcile(self, max_attempts: int, limit: int = 20) -> list[tuple[dict, float]]:
        """Rows the cron may act on, oldest first, each with its age in seconds since the last change (server clock)."""
        rows = self.db.sql(
            f"SELECT {self._select()}, unix_timestamp(current_timestamp()) - unix_timestamp(i.updated_at) AS age "
            f"FROM {self.t}.interactions i WHERE i.payout_status IN ('sending', 'pending') "
            f"OR (i.payout_status = 'failed' AND coalesce(i.payout_attempts, 0) < {int(max_attempts)}) "
            f"ORDER BY i.updated_at LIMIT {int(limit)}")
        return [(to_row(r[:len(COLS)]), float(r[len(COLS)] or 0)) for r in rows]

    def rows_for_user(self, user_id: str, since: datetime, limit: int = 5000) -> list[dict]:
        """A user's drops since `since` (UTC), newest first, with the bin's name."""
        rows = self.db.sql(
            f"SELECT {self._select()}, b.name FROM {self.t}.interactions i LEFT JOIN {self.t}.bins b ON b.bin_id = i.bin_id "
            f"WHERE i.user_id = :u AND i.created_at >= CAST(:since AS TIMESTAMP) ORDER BY i.created_at DESC LIMIT {int(limit)}",
            {"u": user_id, "since": since.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")})
        out = []
        for r in rows:
            row = to_row(r[:len(COLS)])
            row["bin_name"] = r[len(COLS)]
            out.append(row)
        return out
