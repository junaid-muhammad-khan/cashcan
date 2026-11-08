"""Accounts in Databricks (schema workspace.cashcan_app, see databricks/app_schema.sql). Interactions and payouts: app/ledger.py.

Delta cannot enforce unique keys, so uniqueness lives in the statements: users are created with MERGE on auth0_sub.
"""
from __future__ import annotations

import re
import time
import uuid

from .databricks_store import DatabricksFaces

APP_SCHEMA = "workspace.cashcan_app"
SOLANA_ADDR_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
USER_COLS = "user_id, auth0_sub, username, pseudonym, sol_wallet"


PROFILE_TTL_SECONDS = 20.0  # a profile is reused this long per server instance; any write forgets it


class Accounts:
    def __init__(self, db: DatabricksFaces, schema: str = APP_SCHEMA, clock=time.monotonic):
        self.db, self.t, self._clock = db, schema, clock
        self._cache: dict[str, tuple[float, dict]] = {}

    @staticmethod
    def _user(r: list) -> dict:
        user = dict(zip(("user_id", "auth0_sub", "username", "pseudonym", "sol_wallet"), r[:5]))
        user["face_enrolled"] = len(r) > 5 and str(r[5]).lower() == "true"
        return user

    def forget(self, user_id: str | None = None) -> None:
        """Drop cached profiles (everyone, or one user) after something changed."""
        for sub in [k for k, (_, u) in self._cache.items() if user_id is None or u["user_id"] == user_id]:
            del self._cache[sub]

    def user_by_sub(self, sub: str) -> dict | None:
        """The profile incl. face_enrolled, in ONE query, cached briefly (every Databricks round trip costs ~1 s)."""
        hit = self._cache.get(sub)
        if hit and self._clock() - hit[0] < PROFILE_TTL_SECONDS:
            return hit[1]
        rows = self.db.sql(
            f"SELECT u.user_id, u.auth0_sub, u.username, u.pseudonym, u.sol_wallet, "
            f"EXISTS (SELECT 1 FROM {self.db.schema}.users f WHERE f.user_id = u.user_id) AS face_enrolled "
            f"FROM {self.t}.users u WHERE u.auth0_sub = :s LIMIT 1", {"s": sub})
        if not rows:
            return None
        self._cache[sub] = (self._clock(), self._user(rows[0]))
        return self._cache[sub][1]

    def get_or_create_user(self, sub: str) -> dict:
        """Known user: one cached query. First login creates the row with MERGE on auth0_sub, so two simultaneous
        first requests still make one user."""
        user = self.user_by_sub(sub)
        if user:
            return user
        self.db.sql(
            f"MERGE INTO {self.t}.users t USING (SELECT :s AS auth0_sub, :id AS user_id) s ON t.auth0_sub = s.auth0_sub "
            f"WHEN NOT MATCHED THEN INSERT (user_id, auth0_sub, created_at) VALUES (s.user_id, s.auth0_sub, current_timestamp())",
            {"s": sub, "id": uuid.uuid4().hex})
        return self.user_by_sub(sub)

    def delete_profile(self, user_id: str) -> None:
        """Remove an account's profile row (its face data is deleted separately). Interaction history is kept."""
        self.db.sql(f"DELETE FROM {self.t}.users WHERE user_id = :u", {"u": user_id})
        self.forget(user_id)

    def update_profile(self, user_id: str, username: str | None, pseudonym: str | None, wallet: str | None) -> None:
        if wallet is not None and not SOLANA_ADDR_RE.match(wallet):
            raise ValueError("That does not look like a Solana wallet address.")
        for col, val in (("username", username), ("pseudonym", pseudonym), ("sol_wallet", wallet)):
            if val is not None:
                self.db.sql(f"UPDATE {self.t}.users SET {col} = :v WHERE user_id = :u", {"v": val.strip(), "u": user_id})
        self.forget(user_id)

    def leaderboard(self, limit: int = 20) -> list[dict]:
        rows = self.db.sql(f"SELECT display_name, sol_earned, items FROM {self.t}.leaderboard LIMIT {int(limit)}")
        return [{"rank": n, "name": r[0], "sol_earned": float(r[1]), "items": int(r[2])} for n, r in enumerate(rows, 1)]
