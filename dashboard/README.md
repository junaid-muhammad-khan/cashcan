# CashCan dashboard (Databricks AI/BI)

AI/BI (Lakeview) dashboard over `activity_log` — the table `backend/src/activityLog.ts` writes one row to per payout decision.

**Live (demo data):** https://dbc-38b8f0fd-7cd5.cloud.databricks.com/sql/dashboardsv3/01f1db16c4d811588d4df6a43f9d2aea/published

## What it shows

- Items per day by bin (cans / organics / waste) and share by bin
- Contamination rate by item — where people sort wrong
- Daily payout-outcome mix: Paid vs. the anti-abuse gates (low confidence, cameras disagree, not reward-eligible)
- Per-user table and recent-events table (with tx signature)
- Filters page: date range, bin, item

## Files
| File | Purpose |
|---|---|
| `build_dashboard.py` | Generates `cashcan_dashboard.lvdash.json` (one dataset, measures, widgets, theme) |
| `deploy.py` | Creates (or `--id` updates) the dashboard via the Lakeview REST API and publishes it |
| `seed_demo.sql` | Builds `workspace.cashcan_demo.activity_log`: same schema, ~1,400 synthetic events over 14 days |
| `dbsql.py` | Small SQL Statement API runner used to seed and test queries |

## Demo data vs. the real table
The dashboard currently reads **`workspace.cashcan_demo.activity_log` (synthetic)**. The real
`workspace.cashcan` schema is owned by another teammate, and at build time this account had no
`USE SCHEMA` on it. Once the schema owner runs:

```sql
GRANT USE SCHEMA, SELECT ON SCHEMA workspace.cashcan TO `imjunaid.mkhan@gmail.com`;
```

point the same dashboard at real data:

```bash
python deploy.py --schema cashcan --id 01f1db16c4d811588d4df6a43f9d2aea
```

Do not present the demo numbers as real bin results.
