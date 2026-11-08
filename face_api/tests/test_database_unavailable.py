"""When Databricks can't be reached or says no (stopped warehouse, free daily limit used up), the API answers 503 with a plain
message the website can show, instead of a bare 500. Real bugs (a query that fails) still surface as errors."""
import httpx
import pytest
from fastapi.testclient import TestClient

from app import config
from app.accounts import Accounts
from app.auth import TokenVerifier
from app.databricks_store import DatabaseUnavailable, DatabricksError, DatabricksFaces
from app.game import GameScores
from app.main import create_app
from app.sessions import SessionManager
from app.store import FaceStore
from tests.conftest import FakeEngine
from tests.test_accounts_api import AUD, DOMAIN, Resolver, auth

LIMIT_BODY = ('{"error_code":"BAD_REQUEST","message":"Sorry, cannot run the resource because you have hit your free daily limit. '
              'Please come back again tomorrow.","details":[{"denyReason":"COMMUNITY_EDITION_CREDIT_EXHAUSTED"}]}')


class DownDB:
    """A database whose every statement fails the way `error` says."""
    schema = "workspace.cashcan_faces"

    def __init__(self, error):
        self.error = error

    def sql(self, stmt, params=None):
        raise self.error


def client(error, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "REQUIRE_LIVENESS", False)
    db = DownDB(error)
    app = create_app(engine=FakeEngine(), store=FaceStore(str(tmp_path / "f.db")), sessions=SessionManager(),
                     accounts=Accounts(db), verifier=TokenVerifier(DOMAIN, AUD, key_resolver=Resolver()),
                     payouts=object(), game=GameScores(db))
    return TestClient(app, raise_server_exceptions=False)


def test_a_stopped_or_refusing_database_gives_a_clear_503(tmp_path, monkeypatch):
    c = client(DatabaseUnavailable("POST /api/2.0/sql/statements -> HTTP 400: could not be processed by the warehouse"), tmp_path, monkeypatch)
    r = c.get("/me", headers=auth())
    assert r.status_code == 503 and r.headers["retry-after"] == "600"
    d = r.json()["detail"]
    assert d["code"] == "database_unavailable" and d["daily_limit"] is False
    assert "try again later" in d["message"] and "database" in d["message"]


def test_the_free_daily_limit_is_flagged(tmp_path, monkeypatch):
    c = client(DatabaseUnavailable(f"POST /api/2.0/sql/warehouses/x/start -> HTTP 400: {LIMIT_BODY}"), tmp_path, monkeypatch)
    d = c.get("/me", headers=auth()).json()["detail"]
    assert d["code"] == "database_unavailable" and d["daily_limit"] is True


def test_the_game_leaderboard_says_the_same_thing(tmp_path, monkeypatch):
    c = client(DatabaseUnavailable("HTTP 400"), tmp_path, monkeypatch)
    assert c.get("/game/leaderboard?period=week").status_code == 503
    assert c.get("/game/leaderboard?period=week").json()["detail"]["code"] == "database_unavailable"


def test_pages_that_need_no_database_keep_working(tmp_path, monkeypatch):
    c = client(DatabaseUnavailable("HTTP 400"), tmp_path, monkeypatch)
    assert c.get("/health").status_code == 200
    assert c.get("/rewards").status_code == 200
    assert c.get("/me").status_code == 401            # still checked before the database is touched


def test_a_real_query_bug_is_not_dressed_up_as_an_outage(tmp_path, monkeypatch):
    c = client(DatabricksError("SQL failed: {'state': 'FAILED', 'error': 'syntax error'}"), tmp_path, monkeypatch)
    assert c.get("/me", headers=auth()).status_code == 500


# ---- the adapter raises the right error
def faces(handler):
    return DatabricksFaces(host="h.example", token="t", warehouse_id="w", transport=httpx.MockTransport(handler))


def test_http_refusals_and_network_failures_are_unavailable():
    with pytest.raises(DatabaseUnavailable) as e:
        faces(lambda req: httpx.Response(400, text=LIMIT_BODY)).sql("SELECT 1")
    assert e.value.daily_limit is True
    with pytest.raises(DatabaseUnavailable) as e:
        faces(lambda req: httpx.Response(400, text='{"message":"The request could not be processed by the warehouse."}')).sql("SELECT 1")
    assert e.value.daily_limit is False

    def boom(req):
        raise httpx.ConnectTimeout("slow", request=req)

    with pytest.raises(DatabaseUnavailable):
        faces(boom).sql("SELECT 1")


def test_a_failed_statement_is_a_plain_databricks_error():
    ok = lambda req: httpx.Response(200, json={"statement_id": "1", "status": {"state": "FAILED", "error": {"message": "bad sql"}}})
    with pytest.raises(DatabricksError) as e:
        faces(ok).sql("SELECT nope")
    assert not isinstance(e.value, DatabaseUnavailable)
