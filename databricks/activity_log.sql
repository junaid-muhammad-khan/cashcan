-- Real activity log table for the Solana payout backend (backend/src/activityLog.ts).
-- Run once in a SQL warehouse before the first real (non-dry-run) payout.
-- Schema must match activityLog.ts's INSERT and dashboard/seed_demo.sql's columns exactly.
CREATE SCHEMA IF NOT EXISTS workspace.cashcan;

CREATE TABLE IF NOT EXISTS workspace.cashcan.activity_log (
  event_id              STRING NOT NULL,
  ts                    TIMESTAMP NOT NULL,
  user_id               STRING,
  item_label            STRING,
  bin_decision          STRING,
  contaminated          BOOLEAN,
  contamination_score   DOUBLE,
  classifier_confidence DOUBLE,
  top_cam_label         STRING,
  front_cam_label       STRING,
  reward_eligible       BOOLEAN NOT NULL,
  payout_sol            DOUBLE NOT NULL,
  payout_tx_sig         STRING
);
