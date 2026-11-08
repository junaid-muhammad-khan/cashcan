-- Migration 002: server-side rewards and payouts on workspace.cashcan_app.interactions (see face_api/app/ledger.py).
-- Adds columns only, never drops data. Run once, statement by statement (dashboard/dbsql.py -f databricks/002_interactions_payouts.sql).
-- ALTER TABLE ... ADD COLUMNS fails if a column already exists, so a second run stops at the first statement and changes nothing.

ALTER TABLE workspace.cashcan_app.interactions ADD COLUMNS (
  reward_cents    INT       COMMENT 'reward owed in CAD cents, decided by face_api/app/rewards.py (never by the bin)',
  lamports        BIGINT    COMMENT 'lamports actually paid (set when paid)',
  cad_per_sol     DOUBLE    COMMENT 'SOL/CAD rate used for this payout, at the moment it was sent',
  rate_source     STRING    COMMENT 'where that rate came from (Coinbase, CoinGecko, Kraken)',
  payout_error    STRING    COMMENT 'last payout error, if any',
  payout_attempts INT       COMMENT 'number of sends tried',
  payout_wallet   STRING    COMMENT 'wallet the payout was sent to (snapshot at claim time)',
  paid_at         TIMESTAMP,
  updated_at      TIMESTAMP COMMENT 'last status change, the reconcile job measures backoff and stuck rows from this',
  reason          STRING    COMMENT 'why reward_cents is 0: not_recognised | low_confidence | not_reward_eligible | cooldown'
);

-- payout_status is now: none | held | pending | sending | paid | failed. reward_lamports is kept for compatibility and set to
-- the paid lamports. Backfill the rows written before this migration (old placeholder lamports are not CAD, so they get 0 cents
-- unless already paid, their reward_lamports stays as it was).
UPDATE workspace.cashcan_app.interactions
SET reward_cents = CASE WHEN payout_status = 'paid' OR (user_id IS NOT NULL AND item_class = 'cans') THEN 5 ELSE 0 END,
    lamports = CASE WHEN payout_status = 'paid' THEN reward_lamports END,
    payout_attempts = coalesce(payout_attempts, 0),
    updated_at = coalesce(updated_at, created_at)
WHERE reward_cents IS NULL;

ALTER TABLE workspace.cashcan_app.interactions ALTER COLUMN payout_status COMMENT 'none | held | pending | sending | paid | failed';

-- Leaderboard: paid lamports (new rows) with the old column as fallback. Pseudonym only, never username or email.
CREATE OR REPLACE VIEW workspace.cashcan_app.leaderboard AS
SELECT
  COALESCE(u.pseudonym, concat('Sorter ', substr(u.user_id, 1, 4))) AS display_name,
  SUM(COALESCE(i.lamports, i.reward_lamports)) / 1e9 AS sol_earned,
  COUNT(*) AS items
FROM workspace.cashcan_app.interactions i
JOIN workspace.cashcan_app.users u ON u.user_id = i.user_id
WHERE i.payout_status = 'paid'
GROUP BY u.user_id, COALESCE(u.pseudonym, concat('Sorter ', substr(u.user_id, 1, 4)))
ORDER BY sol_earned DESC;

-- City dashboard (dashboard/build_dashboard.py). One row per drop. Pseudonym only: never username, email, wallet or session.
CREATE OR REPLACE VIEW workspace.cashcan_app.city_activity AS
SELECT
  i.interaction_id,
  i.created_at                                    AS ts,
  i.bin_id,
  COALESCE(b.name, i.bin_id)                      AS bin_name,
  COALESCE(b.location, 'Unknown location')        AS bin_location,
  i.item_class,
  i.confidence,
  i.user_id IS NOT NULL                           AS recognised,
  CASE WHEN i.user_id IS NULL THEN 'Unrecognised' ELSE 'Recognised' END AS recognition,
  CASE WHEN i.user_id IS NULL THEN NULL
       ELSE COALESCE(u.pseudonym, concat('Sorter ', substr(i.user_id, 1, 4))) END AS sorter,
  COALESCE(i.reward_cents, 0)                     AS reward_cents,
  CASE WHEN i.payout_status = 'paid' THEN COALESCE(i.lamports, i.reward_lamports) ELSE 0 END AS lamports_paid,
  CASE WHEN i.payout_status = 'paid' THEN COALESCE(i.lamports, i.reward_lamports) / 1e9 ELSE 0 END AS sol_paid,
  CASE WHEN i.payout_status = 'paid' AND i.cad_per_sol IS NOT NULL
       THEN COALESCE(i.lamports, i.reward_lamports) / 1e9 * i.cad_per_sol ELSE 0 END AS cad_paid,
  i.payout_status,
  i.reason,
  i.tx_signature
FROM workspace.cashcan_app.interactions i
LEFT JOIN workspace.cashcan_app.bins b ON b.bin_id = i.bin_id
LEFT JOIN workspace.cashcan_app.users u ON u.user_id = i.user_id;
