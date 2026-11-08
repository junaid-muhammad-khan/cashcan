"""The kids' sorting game: server-side scoring, checks on what the browser claims, leaderboard, nicknames."""
import re
import time

import pytest
from fastapi.testclient import TestClient

from app import config
from app.accounts import Accounts
from app.auth import TokenVerifier
from app.game import GameScores, accuracy_of, check_result, clean_nickname, level_of, score_of
from app.main import create_app
from app.sessions import SessionManager
from app.store import FaceStore
from tests.conftest import FakeEngine
from tests.test_accounts_api import AUD, DOMAIN, Resolver, auth


class GameDB:
    """Plays users + game_scores in memory for exactly the statements app/game.py sends."""

    schema = "workspace.cashcan_faces"

    def __init__(self):
        self.users, self.scores, self.created, self.now = {}, {}, 0, 1000.0

    def sql(self, stmt, params=None):
        p = params or {}
        if stmt.startswith("CREATE TABLE IF NOT EXISTS workspace.cashcan_app.game_scores"):
            self.created += 1
            return []
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
        if "SELECT COUNT(*) FROM workspace.cashcan_app.game_scores WHERE user_id" in stmt:
            secs = int(re.search(r"INTERVAL (\d+) SECONDS", stmt).group(1))
            n = sum(1 for sid, r in self.scores.items() if r["user"] == p["u"] and sid != p["g"] and r["at"] > self.now - secs)
            return [[str(n)]]
        if stmt.startswith("MERGE INTO workspace.cashcan_app.game_scores"):
            if p["g"] not in self.scores:
                self.scores[p["g"]] = {"user": p["u"], "score": int(p["sc"]), "correct": int(p["c"]), "wrong": int(p["w"]),
                                       "spilled": int(p["sp"]), "streak": int(p["bs"]), "level": int(p["lv"]), "at": self.now}
            return []
        if stmt.startswith("SELECT MAX(score)"):
            week = "7 DAYS" in stmt
            mine = [r["score"] for r in self.scores.values() if r["user"] == p["u"] and (not week or r["at"] >= self.now - 7 * 86400)]
            return [[str(max(mine)) if mine else None]]
        if "SELECT COUNT(*) FROM (SELECT user_id, MAX(score)" in stmt:
            best = {}
            for r in self.scores.values():
                if "7 DAYS" in stmt and r["at"] < self.now - 7 * 86400:
                    continue
                best[r["user"]] = max(best.get(r["user"], 0), r["score"])
            return [[str(sum(1 for s in best.values() if s > int(p["sc"])))]]
        if "ROW_NUMBER() OVER" in stmt:
            per = {}
            for r in sorted(self.scores.values(), key=lambda r: (-r["score"], r["at"])):
                if "7 DAYS" in stmt and r["at"] < self.now - 7 * 86400:
                    continue
                per.setdefault(r["user"], r)
            rows = sorted(per.items(), key=lambda kv: (-kv[1]["score"], kv[1]["at"]))
            names = {u["user_id"]: u.get("pseudonym") or f"Sorter {u['user_id'][:4]}" for u in self.users.values()}
            lim = int(re.search(r"LIMIT (\d+)", stmt).group(1))
            return [[uid, names[uid], str(r["score"]), str(r["correct"]), str(r["wrong"]), str(r["spilled"]), str(r["streak"]), str(r["level"])]
                    for uid, r in rows[:lim]]
        raise AssertionError(stmt)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "REQUIRE_LIVENESS", False)
    db = GameDB()
    app = create_app(engine=FakeEngine(), store=FaceStore(str(tmp_path / "f.db")), sessions=SessionManager(),
                     accounts=Accounts(db), verifier=TokenVerifier(DOMAIN, AUD, key_resolver=Resolver()),
                     payouts=object(), game=GameScores(db))
    return TestClient(app), db


def result(**kw):
    r = {"game_id": "game-0001-abcd", "correct": 20, "wrong": 2, "spilled": 1, "best_streak": 9, "duration_ms": 60_000}
    r.update(kw)
    return r


def test_score_is_worked_out_by_the_server():
    assert score_of(20, 9) == 20 * 10 + 9 * 5
    assert level_of(0) == 1 and level_of(7) == 1 and level_of(8) == 2 and level_of(24) == 4
    assert accuracy_of(20, 2, 1) == 87 and accuracy_of(0, 0, 0) == 0
    r = check_result({**result(), "score": 999999})  # a made-up score from the browser is ignored
    assert r["score"] == 245 and r["level"] == 3


@pytest.mark.parametrize("bad", [
    {"correct": -1}, {"correct": 1.5}, {"correct": "9"}, {"correct": True}, {"correct": 100000},
    {"wrong": 4}, {"wrong": 2, "spilled": 2}, {"best_streak": 21}, {"duration_ms": 1000},   # 20 items in 1 s
    {"game_id": "x"}, {"game_id": "bad id with spaces!"},
])
def test_impossible_results_are_refused(bad):
    with pytest.raises(ValueError):
        check_result(result(**bad))


def test_save_needs_login_and_good_numbers(env):
    c, _ = env
    assert c.post("/game/scores", json=result()).status_code == 401
    r = c.post("/game/scores", json=result(duration_ms=5), headers=auth())
    assert r.status_code == 400 and "too fast" in r.json()["detail"]


def test_save_returns_score_best_and_rank_and_is_idempotent(env):
    c, db = env
    first = c.post("/game/scores", json=result(), headers=auth()).json()
    assert first == {"saved": True, "score": 245, "best": 245, "personal_best": True, "rank": 1}
    again = c.post("/game/scores", json=result(), headers=auth()).json()          # same game_id, e.g. a retry
    assert again["saved"] and len(db.scores) == 1 and again["personal_best"] is False
    assert db.created == 1                                                          # the table is created once


def test_second_game_too_soon_is_refused_then_allowed(env):
    c, db = env
    c.post("/game/scores", json=result(), headers=auth())
    r = c.post("/game/scores", json=result(game_id="game-0002-abcd", correct=30, best_streak=10), headers=auth())
    assert r.status_code == 429
    db.now += 20
    ok = c.post("/game/scores", json=result(game_id="game-0002-abcd", correct=30, best_streak=10, duration_ms=90_000), headers=auth()).json()
    assert ok["personal_best"] and ok["best"] == 350


def test_a_game_with_nothing_sorted_is_not_stored(env):
    c, db = env
    r = c.post("/game/scores", json=result(correct=0, best_streak=0, wrong=2, spilled=1, duration_ms=9000), headers=auth()).json()
    assert r["saved"] is False and not db.scores


def test_leaderboard_is_public_ranked_nicknames_only_and_marks_me(env):
    c, db = env
    c.post("/game/scores", json=result(), headers=auth(sub="auth0|ana"))
    c.put("/game/nickname", json={"nickname": "Ana the Brave"}, headers=auth(sub="auth0|ana"))
    db.now += 20
    c.post("/game/scores", json=result(game_id="game-0003-abcd", correct=40, best_streak=15, duration_ms=120_000), headers=auth(sub="auth0|ben"))

    board = c.get("/game/leaderboard?period=all").json()                            # no login needed to look
    assert [r["rank"] for r in board["leaderboard"]] == [1, 2] and board["me"] is None
    assert board["leaderboard"][0]["score"] == 475 and board["leaderboard"][0]["name"].startswith("Sorter ")
    assert board["leaderboard"][1]["name"] == "Ana the Brave" and board["leaderboard"][1]["accuracy"] == 87
    assert not any(r["is_me"] for r in board["leaderboard"])
    assert all(set(r) == {"rank", "name", "score", "correct", "best_streak", "level", "accuracy", "is_me"} for r in board["leaderboard"])

    mine = c.get("/game/leaderboard?period=week", headers=auth(sub="auth0|ana")).json()
    assert [r["is_me"] for r in mine["leaderboard"]] == [False, True] and mine["me"] == {"best": 245, "rank": 2}
    assert c.get("/game/leaderboard?period=forever").status_code == 400


def test_old_scores_drop_off_the_weekly_board_but_stay_in_all_time(env):
    c, db = env
    c.post("/game/scores", json=result(), headers=auth())
    db.now += 8 * 86400
    week = c.get("/game/leaderboard?period=week", headers=auth()).json()
    assert week["leaderboard"] == [] and week["me"] == {"best": None, "rank": None}   # "your best this week" is this week's best
    allt = c.get("/game/leaderboard?period=all", headers=auth()).json()
    assert len(allt["leaderboard"]) == 1 and allt["me"] == {"best": 245, "rank": 1}


@pytest.mark.parametrize("name,ok", [
    ("Ana", True), ("Mia 7", True), ("Sorter-Max_1", True), ("  Zoe   Q  ", True),
    ("A", False), ("x" * 17, False), ("", False), ("a@b.co", False), ("call 6045551234", False),
    ("visit www home", False), ("<b>hi</b>", False), ("-start", False),
])
def test_nicknames(name, ok):
    if ok:
        assert clean_nickname(name) == " ".join(name.split())
    else:
        with pytest.raises(ValueError):
            clean_nickname(name)


def test_nickname_endpoint_saves_and_rejects(env):
    c, db = env
    assert c.put("/game/nickname", json={"nickname": "Ace"}).status_code == 401
    assert c.put("/game/nickname", json={"nickname": "a@b.com"}, headers=auth()).status_code == 400
    assert c.put("/game/nickname", json={"nickname": "Ace"}, headers=auth()).json() == {"nickname": "Ace"}
    assert c.get("/me", headers=auth()).json()["pseudonym"] == "Ace"


# ---- reads are cached briefly, so repeated page views do not wake the warehouse
def test_the_leaderboard_is_read_once_per_window_and_a_saved_score_refreshes_it():
    from app.cache import TTLCache

    class CountingDB:
        schema = "workspace.cashcan_faces"

        def __init__(self):
            self.queries = 0

        def sql(self, stmt, params=None):
            if "ROW_NUMBER" in stmt:
                self.queries += 1
                return [["u1", "Ace", "50", "5", "0", "0", "5", "1"]]
            return []

    db = CountingDB()
    g = GameScores(db)
    g._ready = True
    for _ in range(5):
        assert g.leaderboard("week", 10)[0]["name"] == "Ace"
    assert db.queries == 1
    g.invalidate()
    g.leaderboard("week", 10)
    assert db.queries == 2


def test_ttlcache_expires_and_does_not_cache_errors():
    from app.cache import TTLCache

    now = [0.0]
    c = TTLCache(10, clock=lambda: now[0])
    calls = []
    assert c.get("k", lambda: calls.append(1) or "v") == "v" and c.get("k", lambda: calls.append(1) or "w") == "v"
    assert len(calls) == 1
    now[0] = 11
    assert c.get("k", lambda: "w") == "w"

    def boom():
        raise RuntimeError("db down")

    for _ in range(2):
        with pytest.raises(RuntimeError):
            c.get("e", boom)
