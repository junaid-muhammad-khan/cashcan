import numpy as np
import pytest

from app import config, main
from app.databricks_store import DatabricksStore


def vec(seed):
    v = np.random.default_rng(seed).normal(size=512).astype(np.float32)
    return v / np.linalg.norm(v)


class StubDB:
    def __init__(self):
        self.users, self.t, self.pulls, self.sync_args = {}, [], 0, []

    def user_exists(self, u): return u in self.users
    def get_wallet(self, u): return self.users.get(u)

    def push_user(self, u, w, embs, sync=True):
        self.users[u] = w
        self.t += [(u, e) for e in embs]
        self.sync_args.append(sync)

    def delete_user(self, u, sync=True):
        if u not in self.users:
            return False
        self.users.pop(u)
        self.t = [x for x in self.t if x[0] != u]
        self.sync_args.append(sync)
        return True

    def pull_all(self):
        self.pulls += 1
        return [u for u, _ in self.t], np.array([e for _, e in self.t], np.float32).reshape(len(self.t), 512), dict(self.users)


def test_store_roundtrip_without_blocking_index_sync():
    db = StubDB()
    s = DatabricksStore(db)
    s.add_user("alice", "W", [vec(1), vec(2)])
    assert s.user_exists("alice") and s.wallet("alice") == "W"
    owners, mat = s.all_embeddings()
    assert owners == ["alice", "alice"] and mat.shape == (2, 512)
    assert s.embeddings_for("alice").shape == (2, 512) and s.embeddings_for("bob").shape == (0, 512)
    assert s.delete_user("alice") and not s.delete_user("alice")
    assert s.all_embeddings()[0] == []
    assert db.sync_args[:2] == [False, False]  # request path never waits for the (slow) Vector Search sync


def test_cache_avoids_a_query_per_match_and_expires():
    db, now = StubDB(), [0.0]
    s = DatabricksStore(db, cache_seconds=30, clock=lambda: now[0])
    s.add_user("alice", "W", [vec(1)])
    s.all_embeddings(); s.all_embeddings(); s.embeddings_for("alice")
    assert db.pulls == 1
    now[0] = 31
    s.all_embeddings()
    assert db.pulls == 2


def test_make_store_selection(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "STORE", "sqlite")
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "x.db"))
    assert type(main.make_store()).__name__ == "FaceStore"
    monkeypatch.setattr(config, "STORE", "databricks")
    for k in ("DATABRICKS_HOST", "DATABRICKS_TOKEN", "DATABRICKS_WAREHOUSE_ID"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(Exception, match="DATABRICKS"):
        main.make_store()
    for k in ("DATABRICKS_HOST", "DATABRICKS_TOKEN", "DATABRICKS_WAREHOUSE_ID"):
        monkeypatch.setenv(k, "h.example" if k.endswith("HOST") else "x")
    assert type(main.make_store()).__name__ == "DatabricksStore"
