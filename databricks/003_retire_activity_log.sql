-- Migration 003: retire workspace.cashcan.activity_log. workspace.cashcan_app.interactions is the single source of truth.
-- Nothing writes activity_log any more (backend/src/activityLog.ts is gone). The old table is RENAMED, not dropped, and a
-- read-only view with the same columns takes its name, so anything that still reads activity_log keeps working on real data.
--
-- Must be run by the owner of the workspace.cashcan schema. The view also needs the reader to have SELECT on
-- workspace.cashcan_app.interactions. Run after 002_interactions_payouts.sql.

ALTER TABLE workspace.cashcan.activity_log RENAME TO workspace.cashcan.activity_log_legacy;

CREATE OR REPLACE VIEW workspace.cashcan.activity_log AS
SELECT
  i.interaction_id                         AS event_id,
  i.created_at                             AS ts,
  i.user_id,
  i.item_class                             AS item_label,
  i.item_class                             AS bin_decision,
  CAST(NULL AS BOOLEAN)                    AS contaminated,          -- contamination is not detected
  CAST(NULL AS DOUBLE)                     AS contamination_score,
  i.confidence                             AS classifier_confidence,
  CAST(NULL AS STRING)                     AS top_cam_label,
  CAST(NULL AS STRING)                     AS front_cam_label,
  COALESCE(i.reward_cents, 0) > 0          AS reward_eligible,
  CASE WHEN i.payout_status = 'paid' THEN COALESCE(i.lamports, i.reward_lamports) / 1e9 ELSE 0 END AS payout_sol,
  i.tx_signature                           AS payout_tx_sig
FROM workspace.cashcan_app.interactions i;
