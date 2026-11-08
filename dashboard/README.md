# CashCan city dashboard (Databricks AI/BI)

AI/BI (Lakeview) dashboard over the view `workspace.cashcan_app.city_activity` (`databricks/002_interactions_payouts.sql`): every drop
recorded by a bin, joined with its bin and, for recognised people, their **pseudonym only** (never username, email or wallet).

**Live:** https://dbc-38b8f0fd-7cd5.cloud.databricks.com/sql/dashboardsv3/01f1db16c4d811588d4df6a43f9d2aea/published

## What it shows
- KPIs: items sorted (daily sparkline), share of recognised drops, devnet SOL paid, paid value in CAD (at the rate used for each payout)
- Items per day by bin (cans / organics / waste); recognised vs unrecognised drops per day
- SOL and CAD paid per day; payout status mix (paid / held / paying / failed / no reward)
- Activity per bin location; top sorters by pseudonym; recent drops with tx signature
- Filters page: date range, bin location, item

## Files
| File | Purpose |
|---|---|
| `build_dashboard.py` | Generates `cashcan_dashboard.lvdash.json` (one dataset over `city_activity`, measures, widgets, theme) |
| `deploy.py` | Creates (or `--id` updates) the dashboard via the Lakeview REST API and publishes it |
| `dbsql.py` | Small SQL Statement API runner (`-f file.sql` runs a migration statement by statement) |
| `seed_demo.sql` | Old synthetic `activity_log` demo data (no longer used by the dashboard) |

```bash
python build_dashboard.py
python deploy.py --schema cashcan_app --id 01f1db16c4d811588d4df6a43f9d2aea
```

Contamination is not detected by the product, so the dashboard has no contamination widgets.
