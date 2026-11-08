"""Create or update the CashCan AI/BI dashboard via the Lakeview REST API, then publish.

  python deploy.py [--schema cashcan_app] [--id DASHBOARD_ID]

Uses DATABRICKS_SERVER_HOSTNAME / DATABRICKS_TOKEN / DATABRICKS_WAREHOUSE_ID from the env.
"""
import argparse, json, os, urllib.parse, urllib.request
import build_dashboard

HOST = os.environ.get("DATABRICKS_SERVER_HOSTNAME", "dbc-38b8f0fd-7cd5.cloud.databricks.com")
WH = os.environ.get("DATABRICKS_WAREHOUSE_ID", "9a5194b5eb7321ed")
TOKEN = os.environ.get("DATABRICKS_TOKEN", "x")

def call(method, path, body=None, params=None):
    url = f"https://{HOST}{path}" + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    try:
        return json.load(urllib.request.urlopen(req))
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{method} {path} -> {e.code}: {e.read().decode()}")

ap = argparse.ArgumentParser()
ap.add_argument("--schema", default="cashcan_app")
ap.add_argument("--catalog", default="workspace")
ap.add_argument("--id")
ap.add_argument("--parent", default=None)
a = ap.parse_args()

body = {"display_name": "CashCan — City Activity", "warehouse_id": WH,
        "serialized_dashboard": json.dumps(build_dashboard.dashboard)}
params = {"dataset_catalog": a.catalog, "dataset_schema": a.schema}
if a.id:
    d = call("PATCH", f"/api/2.0/lakeview/dashboards/{a.id}", body, params)
else:
    me = call("GET", "/api/2.0/preview/scim/v2/Me")["userName"]
    body["parent_path"] = a.parent or f"/Workspace/Users/{me}"
    d = call("POST", "/api/2.0/lakeview/dashboards", body, params)
did = d["dashboard_id"]
call("POST", f"/api/2.0/lakeview/dashboards/{did}/published", {"warehouse_id": WH, "embed_credentials": True})
print(f"dashboard_id={did}\nhttps://{HOST}/sql/dashboardsv3/{did}/published")
