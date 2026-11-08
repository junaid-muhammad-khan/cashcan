"""Tiny runner for the Databricks SQL Statement API: python dbsql.py "SQL" [...] or -f file.sql (split on ';')."""
import json, os, sys, urllib.request
HOST = os.environ.get("DATABRICKS_SERVER_HOSTNAME", "dbc-38b8f0fd-7cd5.cloud.databricks.com")
WH = os.environ.get("DATABRICKS_WAREHOUSE_ID", "9a5194b5eb7321ed")
TOKEN = os.environ.get("DATABRICKS_TOKEN", "x")

def run(sql):
    req = urllib.request.Request(f"https://{HOST}/api/2.0/sql/statements", method="POST",
        data=json.dumps({"warehouse_id": WH, "statement": sql, "wait_timeout": "50s"}).encode(),
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    d = json.load(urllib.request.urlopen(req))
    st = d["status"]
    cols = [c["name"] for c in d.get("manifest", {}).get("schema", {}).get("columns", [])]
    return st["state"], st.get("error", {}).get("message"), cols, d.get("result", {}).get("data_array") or []

if __name__ == "__main__":
    args = sys.argv[1:]
    stmts = [s for s in open(args[1]).read().split(";") if s.strip() and not all(l.strip().startswith("--") or not l.strip() for l in s.splitlines())] if args[0] == "-f" else args
    for s in stmts:
        state, err, cols, rows = run(s)
        print(state, err or "", cols); [print("  ", r) for r in rows[:15]]
