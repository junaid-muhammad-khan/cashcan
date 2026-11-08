import json

import httpx
import numpy as np
import pytest

from app.databricks_store import DatabricksError, DatabricksFaces, MODEL_VERSION, score_to_cosine


class Fake:
    """Records requests and answers the few Databricks endpoints the store uses."""

    def __init__(self):
        self.sql_calls, self.other, self.users, self.rows = [], [], {}, []

    def handler(self, req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content) if req.content else {}
        if req.url.path == "/api/2.0/sql/statements":
            stmt, params = body["statement"], {p["name"]: p["value"] for p in body.get("parameters", [])}
            self.sql_calls.append((stmt, params))
            data = []
            if "SELECT 1 FROM" in stmt:
                data = [["1"]] if params["u"] in self.users else []
            elif "INSERT INTO" in stmt and ".users" in stmt:
                self.users[params["u"]] = params["w"]
            elif "INSERT INTO" in stmt and "face_templates" in stmt:
                self.rows.append(params["u"])
            elif "DELETE FROM" in stmt and "face_templates" in stmt:
                self.rows = [u for u in self.rows if u != params["u"]]
            elif "DELETE FROM" in stmt and ".users" in stmt:
                self.users.pop(params["u"], None)
            return httpx.Response(200, json={"status": {"state": "SUCCEEDED"}, "result": {"data_array": data}})
        self.other.append((req.method, req.url.path, body))
        if req.url.path.endswith("/query"):
            return httpx.Response(200, json={"result": {"data_array": [["alice", 0.9], ["alice", 0.5], ["bob", 0.4]]}})
        return httpx.Response(200, json={})


@pytest.fixture
def db():
    fake = Fake()
    d = DatabricksFaces("https://x.example", "tok", "wh1", transport=httpx.MockTransport(fake.handler))
    return d, fake


def vec(seed):
    v = np.random.default_rng(seed).normal(size=512).astype(np.float32)
    return v / np.linalg.norm(v)


def test_needs_config(monkeypatch):
    for k in ("DATABRICKS_HOST", "DATABRICKS_TOKEN", "DATABRICKS_WAREHOUSE_ID"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(DatabricksError):
        DatabricksFaces()


def test_score_to_cosine_matches_unit_vector_geometry():
    a, b = vec(1), vec(2)
    for _ in range(3):
        b = 0.7 * a + 0.3 * b
        b /= np.linalg.norm(b)
        d2 = float(np.sum((a - b) ** 2))
        assert abs(score_to_cosine(1.0 / (1.0 + d2)) - float(a @ b)) < 1e-6
    assert score_to_cosine(1.0) == 1.0 and score_to_cosine(0) == -1.0


def test_push_stores_user_and_templates_with_bound_strings_then_syncs(db):
    d, fake = db
    assert d.push_user("al'ice; DROP TABLE x", "WALLET", [vec(1), vec(2), vec(3)]) == 3
    stmts = [s for s, _ in fake.sql_calls]
    assert all("al'ice" not in s for s in stmts)           # user input only ever travels as a bound parameter
    assert fake.users == {"al'ice; DROP TABLE x": "WALLET"} and len(fake.rows) == 3
    assert any(p.get("m") == MODEL_VERSION for _, p in fake.sql_calls)
    assert fake.other[-1][:2] == ("POST", "/api/2.0/vector-search/indexes/workspace.cashcan_faces.face_templates_index/sync")
    arr = [s for s in stmts if "face_templates VALUES" in s][0]
    assert arr.count(",") > 500 and "AS ARRAY<FLOAT>" in arr  # a 512-number literal


def test_push_refuses_duplicates(db):
    d, _ = db
    d.push_user("alice", "W", [vec(1)])
    with pytest.raises(DatabricksError, match="already exists"):
        d.push_user("alice", "W", [vec(1)])


def test_delete_removes_everything_and_resyncs(db):
    d, fake = db
    d.push_user("alice", "W", [vec(1), vec(2)])
    assert d.delete_user("alice") and not fake.users and not fake.rows
    assert fake.other[-1][1].endswith("/sync")
    assert d.delete_user("alice") is False


def test_search_returns_best_cosine_per_user(db):
    d, fake = db
    out = d.search(vec(1), k=2)
    assert [u for u, _ in out] == ["alice", "bob"] and out[0][1] > out[1][1]
    assert out[0][1] == pytest.approx(score_to_cosine(0.9))  # best of alice's two hits
    sent = fake.other[-1][2]
    assert len(sent["query_vector"]) == 512 and sent["columns"] == ["user_id"]


def test_http_errors_surface(db):
    d, _ = db
    d._http = httpx.Client(base_url="https://x.example", transport=httpx.MockTransport(lambda r: httpx.Response(403, text="nope")))
    with pytest.raises(DatabricksError, match="403"):
        d.sync_index()


def test_sync_waits_out_a_running_sync_and_does_not_raise_if_it_stays_busy():
    calls = []

    def busy_then_ok(req):
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(400, text='{"message":"Index is not ready to sync yet. Pipeline is in state INITIALIZING"}')
        return httpx.Response(200, json={})

    d = DatabricksFaces("https://x.example", "tok", "wh1", transport=httpx.MockTransport(busy_then_ok))
    assert d.sync_index(sleep=lambda s: None) is True and len(calls) == 3

    always_busy = DatabricksFaces("https://x.example", "tok", "wh1", transport=httpx.MockTransport(
        lambda r: httpx.Response(400, text="Index is not ready to sync yet")))
    assert always_busy.sync_index(retries=3, sleep=lambda s: None) is False  # committed data is not lost to an exception


def test_sync_still_raises_on_real_errors():
    d = DatabricksFaces("https://x.example", "tok", "wh1", transport=httpx.MockTransport(lambda r: httpx.Response(403, text="nope")))
    with pytest.raises(DatabricksError, match="403"):
        d.sync_index(sleep=lambda s: None)


def test_pull_into_adds_only_missing_people(tmp_path):
    from app.store import FaceStore
    from tools.databricks_sync import pull_into

    store = FaceStore(str(tmp_path / "l.db"))
    store.add_user("local-only", "W0", [vec(9)])
    owners = ["alice", "alice", "bob", "local-only"]
    mat = np.stack([vec(1), vec(2), vec(3), vec(4)])
    added = pull_into(store, owners, mat, {"alice": "WA", "bob": "WB", "local-only": "WX"})
    assert added == ["alice", "bob"]
    assert store.wallet("alice") == "WA" and len(store.embeddings_for("alice")) == 2
    assert store.wallet("local-only") == "W0" and len(store.embeddings_for("local-only")) == 1  # untouched
