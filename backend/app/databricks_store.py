"""CashCan face templates in Databricks: a Delta table (source of truth) plus a Vector Search index.

Tables (schema workspace.cashcan_faces):
  users           user_id, wallet, consented_at, created_at, status
  face_templates  template_id, user_id, embedding ARRAY<FLOAT> (512), model_version, created_at   (Change Data Feed on)
Vector Search index: face_templates_index, Delta Sync, self-managed 512-d embeddings, TRIGGERED sync.

Matching at the bin should stay local (pull() the templates once and use app.matching): it is faster and works
offline. search() is the same lookup done inside Databricks, for analytics and for checking the two agree.
Only 512 numbers per template are stored, never photos. Pass the token via DATABRICKS_TOKEN, never in code.
"""
from __future__ import annotations

import os
import uuid

import httpx
import numpy as np

DEFAULT_SCHEMA = "workspace.cashcan_faces"
DEFAULT_INDEX = "workspace.cashcan_faces.face_templates_index"
DEFAULT_ENDPOINT = "cashcan-faces"
MODEL_VERSION = "buffalo_s/w600k_mbf"


class DatabricksError(RuntimeError):
    pass


def score_to_cosine(score: float) -> float:
    """Vector Search scores L2 distance d as 1/(1+d^2). For unit vectors cosine = 1 - d^2/2, so we can
    report the same cosine similarity the local matcher and the thresholds use."""
    if score <= 0:
        return -1.0
    return 1.0 - (1.0 / score - 1.0) / 2.0


def _array_literal(vec: np.ndarray) -> str:
    # floats only, formatted by us: safe to inline (strings always go through bound parameters)
    return "CAST(array(" + ",".join(f"{float(x):.8f}" for x in vec) + ") AS ARRAY<FLOAT>)"


class DatabricksFaces:
    def __init__(self, host: str | None = None, token: str | None = None, warehouse_id: str | None = None,
                 schema: str = DEFAULT_SCHEMA, index: str = DEFAULT_INDEX, endpoint: str = DEFAULT_ENDPOINT,
                 transport: httpx.BaseTransport | None = None, timeout: float = 120.0):
        host = host or os.environ.get("DATABRICKS_HOST")
        token = token or os.environ.get("DATABRICKS_TOKEN")
        self.warehouse_id = warehouse_id or os.environ.get("DATABRICKS_WAREHOUSE_ID")
        if not host or not token or not self.warehouse_id:
            raise DatabricksError("Set DATABRICKS_HOST, DATABRICKS_TOKEN and DATABRICKS_WAREHOUSE_ID.")
        if not host.startswith("http"):
            host = "https://" + host
        self.schema, self.index, self.endpoint = schema, index, endpoint
        self._http = httpx.Client(base_url=host.rstrip("/"), headers={"Authorization": f"Bearer {token}"},
                                  timeout=timeout, transport=transport)

    # ---- plumbing
    def _json(self, method: str, path: str, body: dict | None = None) -> dict:
        r = self._http.request(method, path, json=body)
        if r.status_code >= 400:
            raise DatabricksError(f"{method} {path} -> HTTP {r.status_code}: {r.text[:300]}")
        return r.json() if r.content else {}

    def sql(self, statement: str, params: dict[str, str] | None = None) -> list[list]:
        body = {"warehouse_id": self.warehouse_id, "statement": statement, "wait_timeout": "50s",
                "on_wait_timeout": "CONTINUE"}
        if params:
            body["parameters"] = [{"name": k, "value": v, "type": "STRING"} for k, v in params.items()]
        r = self._json("POST", "/api/2.0/sql/statements", body)
        import time

        while r["status"]["state"] in ("PENDING", "RUNNING"):
            time.sleep(2)
            r = self._json("GET", f"/api/2.0/sql/statements/{r['statement_id']}")
        if r["status"]["state"] != "SUCCEEDED":
            raise DatabricksError(f"SQL failed: {r['status']}")
        return r.get("result", {}).get("data_array", [])

    # ---- users and templates
    def user_exists(self, user_id: str) -> bool:
        return bool(self.sql(f"SELECT 1 FROM {self.schema}.users WHERE user_id = :u", {"u": user_id}))

    def push_user(self, user_id: str, wallet: str, embeddings: list[np.ndarray]) -> int:
        """Store a person's consented templates. Refuses duplicates; delete first to re-enroll."""
        if self.user_exists(user_id):
            raise DatabricksError(f"'{user_id}' already exists in Databricks; delete it first to re-enroll.")
        self.sql(f"INSERT INTO {self.schema}.users VALUES (:u, :w, current_timestamp(), current_timestamp(), 'active')",
                 {"u": user_id, "w": wallet})
        for emb in embeddings:
            self.sql(f"INSERT INTO {self.schema}.face_templates VALUES (:t, :u, {_array_literal(emb)}, :m, current_timestamp())",
                     {"t": uuid.uuid4().hex, "u": user_id, "m": MODEL_VERSION})
        self.sync_index()
        return len(embeddings)

    def pull_all(self) -> tuple[list[str], np.ndarray, dict[str, str]]:
        """All active users' templates for local matching: (owners per template, matrix, wallets)."""
        rows = self.sql(f"SELECT t.user_id, t.embedding FROM {self.schema}.face_templates t "
                        f"JOIN {self.schema}.users u ON u.user_id = t.user_id WHERE u.status = 'active'")
        wallets = {u: w for u, w in self.sql(f"SELECT user_id, wallet FROM {self.schema}.users WHERE status = 'active'")}
        import json

        owners = [r[0] for r in rows]
        mat = np.array([json.loads(r[1]) if isinstance(r[1], str) else r[1] for r in rows], np.float32)
        return owners, mat.reshape(len(owners), 512), wallets

    def delete_user(self, user_id: str) -> bool:
        """Hard-delete the person's templates and record (biometric deletion), then refresh the index."""
        if not self.user_exists(user_id):
            return False
        self.sql(f"DELETE FROM {self.schema}.face_templates WHERE user_id = :u", {"u": user_id})
        self.sql(f"DELETE FROM {self.schema}.users WHERE user_id = :u", {"u": user_id})
        self.sync_index()
        return True

    # ---- vector search
    def sync_index(self) -> None:
        self._json("POST", f"/api/2.0/vector-search/indexes/{self.index}/sync")

    def index_status(self) -> dict:
        return self._json("GET", f"/api/2.0/vector-search/indexes/{self.index}").get("status", {})

    def search(self, embedding: np.ndarray, k: int = 3) -> list[tuple[str, float]]:
        """Best cosine per user according to Vector Search, highest first."""
        r = self._json("POST", f"/api/2.0/vector-search/indexes/{self.index}/query",
                       {"columns": ["user_id"], "query_vector": [float(x) for x in embedding], "num_results": k * 3})
        best: dict[str, float] = {}
        for row in r.get("result", {}).get("data_array", []):
            user, score = row[0], float(row[-1])
            best[user] = max(best.get(user, -1.0), score_to_cosine(score))
        return sorted(best.items(), key=lambda kv: kv[1], reverse=True)[:k]
