"""Scores and leaderboard for the kids' sorting game (workspace.cashcan_app.game_scores).

The server never trusts a score from the browser. The client sends what happened (how many items were sorted right,
wrong or spilled, the best streak, how long it lasted) and the server works out the score itself, after checking the
numbers are possible. That stops casual cheating; it cannot stop someone determined, so this board is for fun and
carries no prizes or rewards.

The leaderboard shows nicknames only (the pseudonym, else "Sorter ab12"), never a username or email.
"""
from __future__ import annotations

import re
import uuid

from .databricks_store import DatabricksFaces

APP_SCHEMA = "workspace.cashcan_app"

LIVES = 3
POINTS_PER_ITEM = 10
POINTS_PER_STREAK_ITEM = 5        # bonus for every item in the player's best streak
ITEMS_PER_LEVEL = 8
MIN_MS_PER_ITEM = 600             # nobody can swipe faster than this on average
MAX_ITEMS = 600
MAX_DURATION_MS = 3 * 60 * 60 * 1000
SUBMIT_COOLDOWN_SECONDS = 15
PERIODS = ("week", "all")

GAME_ID_RE = re.compile(r"^[A-Za-z0-9-]{8,64}$")
NICKNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _-]{1,15}$")


def score_of(correct: int, best_streak: int) -> int:
    return correct * POINTS_PER_ITEM + best_streak * POINTS_PER_STREAK_ITEM


def level_of(correct: int) -> int:
    return 1 + correct // ITEMS_PER_LEVEL


def accuracy_of(correct: int, wrong: int, spilled: int) -> int:
    total = correct + wrong + spilled
    return round(100 * correct / total) if total else 0


def clean_nickname(raw: str) -> str:
    """A leaderboard name kids can safely show: 2-16 letters, digits, spaces, '_' or '-', nothing that looks like contact info."""
    name = " ".join((raw or "").split())
    if not NICKNAME_RE.match(name):
        raise ValueError("Use 2 to 16 letters or numbers. Spaces, - and _ are fine.")
    if re.search(r"\d{5,}", name.replace(" ", "")) or "http" in name.lower() or "www" in name.lower():
        raise ValueError("Please don't put phone numbers or links in your name.")
    return name


def check_result(body: dict) -> dict:
    """Validate what the browser says happened; return clean integers. Raises ValueError with a kid-safe message."""
    def num(key: str, hi: int) -> int:
        v = body.get(key)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v != int(v) or not 0 <= v <= hi:
            raise ValueError("That game result doesn't look right.")
        return int(v)

    r = {"correct": num("correct", MAX_ITEMS), "wrong": num("wrong", LIVES), "spilled": num("spilled", LIVES),
         "best_streak": num("best_streak", MAX_ITEMS), "duration_ms": num("duration_ms", MAX_DURATION_MS)}
    if r["wrong"] + r["spilled"] > LIVES or r["best_streak"] > r["correct"]:
        raise ValueError("That game result doesn't look right.")
    if r["duration_ms"] < r["correct"] * MIN_MS_PER_ITEM:
        raise ValueError("That game was too fast to be real.")
    gid = str(body.get("game_id", ""))
    if not GAME_ID_RE.match(gid):
        raise ValueError("That game result doesn't look right.")
    r["game_id"] = gid
    r["score"] = score_of(r["correct"], r["best_streak"])
    r["level"] = level_of(r["correct"])
    return r


class GameScores:
    def __init__(self, db: DatabricksFaces, schema: str = APP_SCHEMA):
        self.db, self.t = db, schema
        self._ready = False

    def ensure_table(self) -> None:
        """Create the table on first use, so no manual SQL step is needed (also in databricks/004_game_scores.sql)."""
        if self._ready:
            return
        self.db.sql(
            f"CREATE TABLE IF NOT EXISTS {self.t}.game_scores (score_id STRING NOT NULL, user_id STRING NOT NULL, score INT NOT NULL, "
            f"correct INT NOT NULL, wrong INT NOT NULL, spilled INT NOT NULL, best_streak INT NOT NULL, level INT NOT NULL, "
            f"duration_ms BIGINT NOT NULL, created_at TIMESTAMP NOT NULL)")
        self._ready = True

    def save(self, user_id: str, result: dict) -> dict:
        """Store one finished game (idempotent on game_id). Returns {saved, score, best, personal_best, rank}."""
        self.ensure_table()
        if result["correct"] == 0:
            return {"saved": False, "score": 0, "best": self.best(user_id), "personal_best": False, "rank": None}
        recent = self.db.sql(
            f"SELECT COUNT(*) FROM {self.t}.game_scores WHERE user_id = :u AND score_id <> :g "
            f"AND created_at > current_timestamp() - INTERVAL {SUBMIT_COOLDOWN_SECONDS} SECONDS", {"u": user_id, "g": result["game_id"]})
        if recent and int(float(recent[0][0])) > 0:
            raise TooFast("Great game! Wait a few seconds before saving another score.")
        before = self.best(user_id)
        self.db.sql(
            f"MERGE INTO {self.t}.game_scores t USING (SELECT :g AS score_id) s ON t.score_id = s.score_id "
            f"WHEN NOT MATCHED THEN INSERT (score_id, user_id, score, correct, wrong, spilled, best_streak, level, duration_ms, created_at) "
            f"VALUES (:g, :u, CAST(:sc AS INT), CAST(:c AS INT), CAST(:w AS INT), CAST(:sp AS INT), CAST(:bs AS INT), CAST(:lv AS INT), "
            f"CAST(:d AS BIGINT), current_timestamp())",
            {"g": result["game_id"], "u": user_id, "sc": str(result["score"]), "c": str(result["correct"]), "w": str(result["wrong"]),
             "sp": str(result["spilled"]), "bs": str(result["best_streak"]), "lv": str(result["level"]), "d": str(result["duration_ms"])})
        best = max(before or 0, result["score"])
        return {"saved": True, "score": result["score"], "best": best, "personal_best": result["score"] > (before or 0),
                "rank": self.rank_of(best, "all")}

    def best(self, user_id: str, period: str = "all") -> int | None:
        self.ensure_table()
        recent = " AND created_at > current_timestamp() - INTERVAL 7 DAYS" if period == "week" else ""
        rows = self.db.sql(f"SELECT MAX(score) FROM {self.t}.game_scores WHERE user_id = :u{recent}", {"u": user_id})
        return int(float(rows[0][0])) if rows and rows[0][0] is not None else None

    def rank_of(self, score: int, period: str) -> int:
        """1 + how many players have a better best score in this period."""
        where = self._where(period)
        rows = self.db.sql(
            f"SELECT COUNT(*) FROM (SELECT user_id, MAX(score) AS s FROM {self.t}.game_scores {where} GROUP BY user_id) WHERE s > CAST(:sc AS INT)",
            {"sc": str(score)})
        return 1 + int(float(rows[0][0])) if rows else 1

    @staticmethod
    def _where(period: str) -> str:
        return "WHERE created_at > current_timestamp() - INTERVAL 7 DAYS" if period == "week" else ""

    def leaderboard(self, period: str = "week", limit: int = 10, me: str | None = None) -> list[dict]:
        """Each player's best game in the period, best first. Nicknames only."""
        self.ensure_table()
        where = self._where(period).replace("WHERE ", "WHERE s.")
        rows = self.db.sql(
            f"SELECT p.user_id, COALESCE(u.pseudonym, concat('Sorter ', substr(p.user_id, 1, 4))) AS name, p.score, p.correct, p.wrong, p.spilled, "
            f"p.best_streak, p.level FROM (SELECT s.user_id, s.score, s.correct, s.wrong, s.spilled, s.best_streak, s.level, "
            f"ROW_NUMBER() OVER (PARTITION BY s.user_id ORDER BY s.score DESC, s.created_at ASC) AS rn, s.created_at "
            f"FROM {self.t}.game_scores s {where}) p JOIN {self.t}.users u ON u.user_id = p.user_id WHERE p.rn = 1 "
            f"ORDER BY p.score DESC, p.created_at ASC LIMIT {int(limit)}")
        out = []
        for n, r in enumerate(rows, 1):
            correct, wrong, spilled = int(float(r[3])), int(float(r[4])), int(float(r[5]))
            out.append({"rank": n, "name": r[1], "score": int(float(r[2])), "correct": correct, "best_streak": int(float(r[6])),
                        "level": int(float(r[7])), "accuracy": accuracy_of(correct, wrong, spilled), "is_me": bool(me) and r[0] == me})
        return out


class TooFast(ValueError):
    """Two scores saved within the cooldown."""


def new_game_id() -> str:  # used by tests; the browser makes its own
    return uuid.uuid4().hex
