"""Builds cashcan_dashboard.lvdash.json: the city's Databricks AI/BI dashboard over the city_activity view
(databricks/002_interactions_payouts.sql: interactions + bins + users' pseudonyms, never usernames or emails).

Usage: python build_dashboard.py            -> writes the JSON
Queries use the bare view name `city_activity`; the catalog/schema is chosen at deploy time (deploy.py --schema cashcan_app).
"""
import json

DS = "ds_city"
DATASET_SQL = [
    "SELECT interaction_id, ts, bin_id, bin_name, bin_location, item_class, confidence,\n",
    "  recognised, recognition, sorter, reward_cents, lamports_paid, sol_paid, cad_paid,\n",
    "  payout_status, reason, tx_signature,\n",
    "  CAST(recognised AS INT) AS is_recognised,\n",
    "  CASE payout_status WHEN 'paid' THEN 'Paid' WHEN 'held' THEN 'Held (no wallet)'\n",
    "       WHEN 'failed' THEN 'Failed (retrying)' WHEN 'pending' THEN 'Paying' WHEN 'sending' THEN 'Paying'\n",
    "       ELSE 'No reward' END AS payout_label\n",
    "FROM city_activity\n",
]
MEASURES = [
    ("Items Sorted", "Count of drops", "COUNT(`interaction_id`)"),
    ("Recognised Share", "Share of drops by a recognised (enrolled) person", "AVG(`is_recognised`)"),
    ("SOL Paid", "Devnet SOL paid out", "SUM(`sol_paid`)"),
    ("CAD Paid", "CAD value of payouts, at the rate used when each was sent", "SUM(`cad_paid`)"),
    ("Rewards Earned", "Reward owed in CAD cents (paid, held or on the way)", "SUM(`reward_cents`)"),
    ("Sorters", "Distinct recognised people", "COUNT(DISTINCT `sorter`)"),
]
PCT = {"type": "number-percent", "decimalPlaces": {"type": "max", "places": 1}}
SOL = {"type": "number-plain", "decimalPlaces": {"type": "max", "places": 6}}
CAD = {"type": "number-currency", "currencyCode": "CAD", "decimalPlaces": {"type": "max", "places": 2}}

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
RECOG_COLORS = [{"value": "Recognised", "color": "#2BB673"}, {"value": "Unrecognised", "color": "#7A8794"}]
PAYOUT_COLORS = [{"value": "Paid", "color": "#2BB673"}, {"value": "Held (no wallet)", "color": "#E3B23C"},
                 {"value": "Failed (retrying)", "color": "#FF7E5C"}, {"value": "Paying", "color": "#4E79A7"},
                 {"value": "No reward", "color": "#C9D1CB"}]
DAY = ("daily(ts)", 'DATE_TRUNC("DAY", `ts`)')


def bar(name, title, fields, x, y, color, p, mappings=None, xtype="temporal", ydisp="Items", yfmt=None, sort=None):
    enc = {"x": {"fieldName": x, "scale": {"type": xtype}, "displayName": "Day" if xtype == "temporal" else x},
           "y": {"fieldName": y, "scale": {"type": "quantitative"}, "displayName": ydisp}}
    if yfmt:
        enc["y"]["format"] = yfmt
    if sort:
        enc["x"]["scale"]["sort"] = sort
    if color:
        enc["color"] = {"fieldName": color, "scale": {"type": "categorical", **({"mappings": mappings} if mappings else {})},
                        "displayName": color.replace("_", " ").capitalize()}
    return {"widget": {"name": name, "queries": q(fields),
            "spec": {"version": 3, "widgetType": "bar", "encodings": enc, "frame": {"title": title, "showTitle": True}}}, "position": p}


overview = [
    text("title", ["# CashCan — City activity\n"], pos(0, 0, 12, 1)),
    text("subtitle", [
        "Every item dropped in a CashCan bin (from `workspace.cashcan_app.interactions`): which bin it went to, whether the "
        "person was recognised, and the cash back paid in devnet SOL (5 cents CAD per can, converted at the live rate when paid). "
        "Sorters appear by pseudonym only. Use the **Filters** page to narrow by date, bin location or item.\n"], pos(0, 1, 12, 1)),
    counter("kpi_items", "Items sorted", "Items Sorted", pos(0, 2, 3, 3), spark=True),
    counter("kpi_recog", "Recognised drops", "Recognised Share", pos(3, 2, 3, 3), fmt=PCT),
    counter("kpi_sol", "SOL paid (devnet)", "SOL Paid", pos(6, 2, 3, 3), fmt=SOL),
    counter("kpi_cad", "Paid, in CAD", "CAD Paid", pos(9, 2, 3, 3), fmt=CAD),
    text("h_volume", ["## Volume\n"], pos(0, 5, 12, 1)),
    bar("daily_by_bin", "Items per day, by bin", [f(*DAY), f("item_class"), m("Items Sorted")],
        "daily(ts)", "measure(Items Sorted)", "item_class", pos(0, 6, 6, 6), BIN_COLORS),
    bar("daily_recognition", "Recognised vs unrecognised drops per day", [f(*DAY), f("recognition"), m("Items Sorted")],
        "daily(ts)", "measure(Items Sorted)", "recognition", pos(6, 6, 6, 6), RECOG_COLORS),
    text("h_rewards", ["## Rewards\n"], pos(0, 12, 12, 1)),
    bar("daily_sol", "SOL paid per day (devnet)", [f(*DAY), m("SOL Paid")], "daily(ts)", "measure(SOL Paid)", None,
        pos(0, 13, 4, 6), ydisp="SOL", yfmt=SOL),
    bar("daily_cad", "Paid per day, in CAD", [f(*DAY), m("CAD Paid")], "daily(ts)", "measure(CAD Paid)", None,
        pos(4, 13, 4, 6), ydisp="CAD", yfmt=CAD),
    {"widget": {"name": "payout_mix", "queries": q([f("payout_label"), m("Items Sorted")]),
        "spec": {"version": 3, "widgetType": "pie", "encodings": {
            "angle": {"fieldName": "measure(Items Sorted)", "scale": {"type": "quantitative"}, "displayName": "Drops"},
            "color": {"fieldName": "payout_label", "scale": {"type": "categorical", "mappings": PAYOUT_COLORS}, "displayName": "Payout"},
            "label": {"show": True}},
            "frame": {"title": "Payout status mix", "showTitle": True}}}, "position": pos(8, 13, 4, 6)},
    text("h_places", ["## Bins and sorters\n"], pos(0, 19, 12, 1)),
    {"widget": {"name": "by_location", "queries": q([f("bin_location"), f("item_class"), m("Items Sorted")]),
        "spec": {"version": 3, "widgetType": "bar", "encodings": {
            "x": {"fieldName": "measure(Items Sorted)", "scale": {"type": "quantitative"}, "displayName": "Items"},
            "y": {"fieldName": "bin_location", "scale": {"type": "categorical", "sort": {"by": "x-reversed"}}, "displayName": "Bin location"},
            "color": {"fieldName": "item_class", "scale": {"type": "categorical", "mappings": BIN_COLORS}, "displayName": "Bin"}},
            "frame": {"title": "Activity per bin location", "showTitle": True}}}, "position": pos(0, 20, 6, 7)},
    {"widget": {"name": "top_sorters", "queries": q([f("sorter"), m("Items Sorted"), m("SOL Paid"), m("CAD Paid")]),
        "spec": {"version": 2, "widgetType": "table", "encodings": {"columns": [
            {"fieldName": "sorter", "displayName": "Sorter (pseudonym)"},
            {"fieldName": "measure(Items Sorted)", "displayName": "Items"},
            {"fieldName": "measure(SOL Paid)", "displayName": "SOL paid", "format": SOL},
            {"fieldName": "measure(CAD Paid)", "displayName": "CAD paid", "format": CAD}]},
            "frame": {"title": "Top sorters (recognised drops only)", "showTitle": True}}}, "position": pos(6, 20, 6, 7)},
    {"widget": {"name": "recent", "queries": q([f(c) for c in ["ts", "bin_name", "item_class", "recognition", "sorter",
                "reward_cents", "payout_label", "sol_paid", "tx_signature"]], disagg=True),
        "spec": {"version": 2, "widgetType": "table", "encodings": {"columns": [
            {"fieldName": "ts", "displayName": "Time"}, {"fieldName": "bin_name", "displayName": "Bin"},
            {"fieldName": "item_class", "displayName": "Item"}, {"fieldName": "recognition", "displayName": "Person"},
            {"fieldName": "sorter", "displayName": "Sorter"}, {"fieldName": "reward_cents", "displayName": "Reward (¢)"},
            {"fieldName": "payout_label", "displayName": "Payout"},
            {"fieldName": "sol_paid", "displayName": "SOL", "format": SOL},
            {"fieldName": "tx_signature", "displayName": "Tx signature (devnet)"}]},
            "frame": {"title": "Recent drops", "showTitle": True}}}, "position": pos(0, 27, 12, 8)},
]

def filt(name, wtype, col, title, p):
    qn = f"q_{name}"
    return {"widget": {"name": name, "queries": q([f(col)], name=qn),
            "spec": {"version": 2, "widgetType": wtype,
                     "encodings": {"fields": [{"fieldName": col, "displayName": title, "queryName": qn}]},
                     "frame": {"title": title, "showTitle": True}}}, "position": p}

filters = [
    filt("f_date", "filter-date-range-picker", "ts", "Date range", pos(0, 0, 4, 2)),
    filt("f_loc", "filter-multi-select", "bin_location", "Bin location", pos(4, 0, 4, 2)),
    filt("f_item", "filter-multi-select", "item_class", "Item", pos(8, 0, 4, 2)),
]

dashboard = {
    "datasets": [{"name": DS, "displayName": "City activity", "queryLines": DATASET_SQL,
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
