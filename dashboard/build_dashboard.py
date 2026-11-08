"""Builds cashcan_dashboard.lvdash.json (Databricks AI/BI dashboard over activity_log).

Usage: python build_dashboard.py            -> writes the JSON
Queries use the bare table name `activity_log`; the catalog/schema are chosen at
deploy time (deploy.py), so the same file works for workspace.cashcan (real) and
workspace.cashcan_demo (seeded demo copy).
"""
import json

DS = "ds_activity"
DATASET_SQL = [
    "SELECT event_id, ts, user_id, item_label, bin_decision, contaminated,\n",
    "  contamination_score, classifier_confidence, top_cam_label, front_cam_label,\n",
    "  reward_eligible, payout_sol, payout_tx_sig,\n",
    "  CASE WHEN contaminated THEN 'Contaminated' ELSE 'Clean' END AS item_condition,\n",
    "  CAST(contaminated AS INT) AS is_contaminated,\n",
    "  CASE WHEN payout_sol > 0 THEN 1 ELSE 0 END AS is_paid,\n",
    "  CASE WHEN payout_sol > 0 THEN 'Paid'\n",
    "       WHEN NOT reward_eligible AND item_label = 'trash' THEN 'Not reward-eligible'\n",
    "       WHEN classifier_confidence < 0.75 THEN 'Low confidence'\n",
    "       WHEN coalesce(top_cam_label, '') <> coalesce(front_cam_label, '') THEN 'Cameras disagree'\n",
    "       ELSE 'Other / cooldown' END AS outcome\n",
    "FROM activity_log\n",
]
MEASURES = [
    ("Items Sorted", "Count of bin events", "COUNT(`event_id`)"),
    ("Contamination Rate", "Share of items flagged contaminated", "AVG(`is_contaminated`)"),
    ("SOL Paid", "Total devnet SOL paid out", "SUM(`payout_sol`)"),
    ("Payout Rate", "Share of items that earned a payout", "AVG(`is_paid`)"),
    ("Active Users", "Distinct users at the bin", "COUNT(DISTINCT `user_id`)"),
]
PCT = {"type": "number-percent", "decimalPlaces": {"type": "max", "places": 1}}
SOL = {"type": "number-plain", "decimalPlaces": {"type": "max", "places": 3}}

def m(name):
    return {"name": f"measure({name})", "expression": f"MEASURE(`{name}`)"}

def f(col, expr=None):
    return {"name": col, "expression": expr or f"`{col}`"}

def q(fields, disagg=False, name="main_query"):
    return [{"name": name, "query": {"datasetName": DS, "fields": fields, "disaggregated": disagg}}]

def pos(x, y, w, h):
    return {"x": x, "y": y, "width": w, "height": h}

def text(name, lines, p):
    return {"widget": {"name": name, "multilineTextboxSpec": {"lines": lines}}, "position": p}

def counter(name, title, measure, p, fmt=None, spark=False):
    fields = [m(measure)]
    enc = {"value": {"fieldName": f"measure({measure})", "displayName": title}}
    if fmt:
        enc["value"]["format"] = fmt
    if spark:
        fields.insert(0, f("daily(ts)", 'DATE_TRUNC("DAY", `ts`)'))
        enc["period"] = {"fieldName": "daily(ts)"}
    return {"widget": {"name": name, "queries": q(fields),
            "spec": {"version": 2, "widgetType": "counter", "encodings": enc,
                     "frame": {"title": title, "showTitle": True}}}, "position": p}

BIN_COLORS = [{"value": "cans", "color": "#2BB673"}, {"value": "organics", "color": "#E3B23C"},
              {"value": "waste", "color": "#7A8794"}]
OUTCOME_COLORS = [{"value": "Paid", "color": "#2BB673"}, {"value": "Low confidence", "color": "#FF7E5C"},
                  {"value": "Cameras disagree", "color": "#C2477A"},
                  {"value": "Not reward-eligible", "color": "#7A8794"}, {"value": "Other / cooldown", "color": "#4E79A7"}]

overview = [
    text("title", ["# CashCan — Bin Activity\n"], pos(0, 0, 12, 1)),
    text("subtitle", [
        "Every item dropped in a CashCan bin: what the classifier saw, which bin it went to, "
        "whether it was contaminated, and whether the devnet SOL payout went through. "
        "Use the **Filters** page to narrow by date, bin or item.\n"], pos(0, 1, 12, 1)),
    counter("kpi_items", "Items sorted", "Items Sorted", pos(0, 2, 3, 3), spark=True),
    counter("kpi_contam", "Contamination rate", "Contamination Rate", pos(3, 2, 3, 3), fmt=PCT),
    counter("kpi_sol", "SOL paid (devnet)", "SOL Paid", pos(6, 2, 3, 3), fmt=SOL),
    counter("kpi_payout_rate", "Payout rate", "Payout Rate", pos(9, 2, 3, 3), fmt=PCT),
    text("h_trends", ["## Volume and bins\n"], pos(0, 5, 12, 1)),
    {"widget": {"name": "daily_by_bin", "queries": q([f("daily(ts)", 'DATE_TRUNC("DAY", `ts`)'),
                f("bin_decision"), m("Items Sorted")]),
        "spec": {"version": 3, "widgetType": "bar", "encodings": {
            "x": {"fieldName": "daily(ts)", "scale": {"type": "temporal"}, "displayName": "Day"},
            "y": {"fieldName": "measure(Items Sorted)", "scale": {"type": "quantitative"}, "displayName": "Items"},
            "color": {"fieldName": "bin_decision", "scale": {"type": "categorical", "mappings": BIN_COLORS}, "displayName": "Bin"}},
            "frame": {"title": "Items per day, by bin", "showTitle": True}}}, "position": pos(0, 6, 8, 6)},
    {"widget": {"name": "bin_share", "queries": q([f("bin_decision"), m("Items Sorted")]),
        "spec": {"version": 3, "widgetType": "pie", "encodings": {
            "angle": {"fieldName": "measure(Items Sorted)", "scale": {"type": "quantitative"}, "displayName": "Items"},
            "color": {"fieldName": "bin_decision", "scale": {"type": "categorical", "mappings": BIN_COLORS}, "displayName": "Bin"},
            "label": {"show": True}},
            "frame": {"title": "Share by bin", "showTitle": True}}}, "position": pos(8, 6, 4, 6)},
    text("h_quality", ["## Where sorting goes wrong\n"], pos(0, 12, 12, 1)),
    {"widget": {"name": "contam_by_item", "queries": q([f("item_label"), m("Contamination Rate")]),
        "spec": {"version": 3, "widgetType": "bar", "encodings": {
            "x": {"fieldName": "measure(Contamination Rate)", "scale": {"type": "quantitative"},
                  "displayName": "Contamination rate", "format": PCT},
            "y": {"fieldName": "item_label", "scale": {"type": "categorical", "sort": {"by": "x-reversed"}}, "displayName": "Item"}},
            "frame": {"title": "Contamination rate by item", "showTitle": True}}}, "position": pos(0, 13, 6, 6)},
    {"widget": {"name": "outcomes", "queries": q([f("daily(ts)", 'DATE_TRUNC("DAY", `ts`)'), f("outcome"), m("Items Sorted")]),
        "spec": {"version": 3, "widgetType": "bar", "mark": {"layout": "stack-100"}, "encodings": {
            "x": {"fieldName": "daily(ts)", "scale": {"type": "temporal"}, "displayName": "Day"},
            "y": {"fieldName": "measure(Items Sorted)", "scale": {"type": "quantitative"}, "displayName": "Items"},
            "color": {"fieldName": "outcome", "scale": {"type": "categorical", "mappings": OUTCOME_COLORS}, "displayName": "Outcome"}},
            "frame": {"title": "Payout outcome mix per day (anti-abuse gates)", "showTitle": True}}}, "position": pos(6, 13, 6, 6)},
    text("h_detail", ["## Users and recent events\n"], pos(0, 19, 12, 1)),
    {"widget": {"name": "top_users", "queries": q([f("user_id"), m("Items Sorted"), m("SOL Paid"), m("Contamination Rate")]),
        "spec": {"version": 2, "widgetType": "table", "encodings": {"columns": [
            {"fieldName": "user_id", "displayName": "User"},
            {"fieldName": "measure(Items Sorted)", "displayName": "Items"},
            {"fieldName": "measure(SOL Paid)", "displayName": "SOL paid", "format": SOL},
            {"fieldName": "measure(Contamination Rate)", "displayName": "Contamination", "format": PCT}]},
            "frame": {"title": "Users", "showTitle": True}}}, "position": pos(0, 20, 4, 8)},
    {"widget": {"name": "recent", "queries": q([f(c) for c in ["ts", "user_id", "item_label", "bin_decision",
                "item_condition", "classifier_confidence", "outcome", "payout_sol", "payout_tx_sig"]], disagg=True),
        "spec": {"version": 2, "widgetType": "table", "encodings": {"columns": [
            {"fieldName": "ts", "displayName": "Time"}, {"fieldName": "user_id", "displayName": "User"},
            {"fieldName": "item_label", "displayName": "Item"}, {"fieldName": "bin_decision", "displayName": "Bin"},
            {"fieldName": "item_condition", "displayName": "Condition"},
            {"fieldName": "classifier_confidence", "displayName": "Confidence", "format": PCT},
            {"fieldName": "outcome", "displayName": "Outcome"},
            {"fieldName": "payout_sol", "displayName": "SOL", "format": SOL},
            {"fieldName": "payout_tx_sig", "displayName": "Tx signature"}]},
            "frame": {"title": "Recent events", "showTitle": True}}}, "position": pos(4, 20, 8, 8)},
]

def filt(name, wtype, col, title, p):
    qn = f"q_{name}"
    return {"widget": {"name": name, "queries": q([f(col)], name=qn),
            "spec": {"version": 2, "widgetType": wtype,
                     "encodings": {"fields": [{"fieldName": col, "displayName": title, "queryName": qn}]},
                     "frame": {"title": title, "showTitle": True}}}, "position": p}

filters = [
    filt("f_date", "filter-date-range-picker", "ts", "Date range", pos(0, 0, 4, 2)),
    filt("f_bin", "filter-multi-select", "bin_decision", "Bin", pos(4, 0, 4, 2)),
    filt("f_item", "filter-multi-select", "item_label", "Item", pos(8, 0, 4, 2)),
]

dashboard = {
    "datasets": [{"name": DS, "displayName": "Bin activity", "queryLines": DATASET_SQL,
                  "columns": [{"displayName": n, "description": d, "expression": e} for n, d, e in MEASURES]}],
    "pages": [
        {"name": "overview", "displayName": "Overview", "pageType": "PAGE_TYPE_CANVAS",
         "layoutVersion": "GRID_V1", "layout": overview},
        {"name": "filters", "displayName": "Filters", "pageType": "PAGE_TYPE_GLOBAL_FILTERS",
         "layoutVersion": "GRID_V1", "layout": filters},
    ],
    "uiSettings": {"theme": {
        "canvasBackgroundColor": {"light": "#F6F8F5", "dark": "#0F1512"},
        "widgetBackgroundColor": {"light": "#FFFFFF", "dark": "#151D19"},
        "widgetBorderColor": {"light": "#FFFFFF", "dark": "#151D19"},
        "fontColor": {"light": "#10201A", "dark": "#E6EEE9"},
        "selectionColor": {"light": "#2272B4", "dark": "#8ACAFF"},
        "visualizationColors": ["#2BB673", "#E3B23C", "#4E79A7", "#C2477A", "#FF7E5C", "#7A8794", "#76B7B2"],
        "widgetHeaderAlignment": "LEFT", "fontFamily": "Inter", "widgetCornerRadius": 12}},
}

if __name__ == "__main__":
    with open("cashcan_dashboard.lvdash.json", "w") as fh:
        json.dump(dashboard, fh, indent=2)
    print("wrote cashcan_dashboard.lvdash.json")
