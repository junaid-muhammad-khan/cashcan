-- Application tables (accounts, bins, interactions) in Databricks. Run once in a SQL warehouse, statement by statement.
-- After this file, run 002_interactions_payouts.sql (payout columns, city_activity view) and, as the workspace.cashcan owner, 003_retire_activity_log.sql.
-- Face templates stay in workspace.cashcan_faces (see face_api/app/databricks_store.py); face_templates.user_id = users.user_id here.
-- NOTE: Delta tables do not enforce PRIMARY KEY or UNIQUE. The code enforces them: users are created with MERGE on auth0_sub,
-- interactions with MERGE on interaction_id (a retried request inserts nothing the second time).
CREATE SCHEMA IF NOT EXISTS workspace.cashcan_app;

CREATE TABLE IF NOT EXISTS workspace.cashcan_app.users (
  user_id    STRING NOT NULL,   -- our id (uuid); face_templates.user_id points here
  auth0_sub  STRING NOT NULL,   -- Auth0 "sub" claim, unique (enforced by MERGE)
  username   STRING,            -- private; never shown on the leaderboard
  pseudonym  STRING,            -- optional public name for the leaderboard
  sol_wallet STRING,            -- payout address (devnet)
  created_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS workspace.cashcan_app.bins (
  bin_id   STRING NOT NULL,
  name     STRING,
  location STRING
);

CREATE TABLE IF NOT EXISTS workspace.cashcan_app.interactions (
  interaction_id  STRING NOT NULL,  -- idempotency key, chosen by the bin
  user_id         STRING,           -- NULL when nobody was recognised (no face data is kept for strangers)
  session_id      STRING,
  bin_id          STRING,
  item_class      STRING,
  confidence      DOUBLE,
  reward_lamports BIGINT NOT NULL,
  payout_status   STRING NOT NULL,  -- none | held | pending | sending | paid | failed (since 002)
  tx_signature    STRING,
  created_at      TIMESTAMP NOT NULL
);

-- Leaderboard is derived, never stored. Shows the pseudonym only (never username or email).
CREATE OR REPLACE VIEW workspace.cashcan_app.leaderboard AS
SELECT
  COALESCE(u.pseudonym, concat('Sorter ', substr(u.user_id, 1, 4))) AS display_name,
  SUM(i.reward_lamports) / 1e9 AS sol_earned,
  COUNT(*) AS items
FROM workspace.cashcan_app.interactions i
JOIN workspace.cashcan_app.users u ON u.user_id = i.user_id
WHERE i.payout_status = 'paid'
GROUP BY u.user_id, COALESCE(u.pseudonym, concat('Sorter ', substr(u.user_id, 1, 4)))
ORDER BY sol_earned DESC;
