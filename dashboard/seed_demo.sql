-- Demo seed for the CashCan dashboard: same schema as workspace.cashcan.activity_log
-- (see backend/src/activityLog.ts), filled with ~14 days of synthetic bin events.
-- Run in a schema you own, never against the real activity_log.
CREATE SCHEMA IF NOT EXISTS workspace.cashcan_demo;
CREATE OR REPLACE TABLE workspace.cashcan_demo.activity_log AS
WITH base AS (
  SELECT id,
    timestampadd(MINUTE, -CAST((pmod(hash(id, 1), 100000) / 100000.0) * 20160 AS INT), current_timestamp()) AS ts,
    concat('user_', lpad(CAST(CAST((pmod(hash(id, 7), 100000) / 100000.0) * 24 AS INT) AS STRING), 2, '0')) AS user_id,
    element_at(array('metal','plastic','glass','cardboard','paper','biological','battery','clothes','shoes','trash'),
               1 + CAST(pow((pmod(hash(id, 3), 100000) / 100000.0), 1.6) * 10 AS INT)) AS item_label,
    (pmod(hash(id, 5), 100000) / 100000.0) AS r_cont, 0.6 + pow((pmod(hash(id, 11), 100000) / 100000.0), 0.4) * 0.4 AS conf, (pmod(hash(id, 13), 100000) / 100000.0) AS r_cam
  FROM range(1, 1401) AS t(id)
), labeled AS (
  SELECT *,
    CASE WHEN item_label IN ('metal','plastic','glass') THEN 'cans'
         WHEN item_label = 'biological' THEN 'organics' ELSE 'waste' END AS bin_decision,
    r_cont < CASE item_label WHEN 'plastic' THEN 0.32 WHEN 'cardboard' THEN 0.28 WHEN 'paper' THEN 0.3
                             WHEN 'biological' THEN 0.12 ELSE 0.15 END AS contaminated
  FROM base
)
SELECT uuid() AS event_id, ts, user_id, item_label, bin_decision, contaminated,
  round(CASE WHEN contaminated THEN 0.55 + r_cont * 0.4 ELSE r_cont * 0.3 END, 3) AS contamination_score,
  round(conf, 3) AS classifier_confidence,
  item_label AS top_cam_label,
  CASE WHEN r_cam < 0.06 THEN 'trash' ELSE item_label END AS front_cam_label,
  item_label <> 'trash' AND conf >= 0.75 AND r_cam >= 0.06 AS reward_eligible,
  CASE WHEN item_label <> 'trash' AND conf >= 0.75 AND r_cam >= 0.06 THEN
    (CASE item_label WHEN 'metal' THEN 0.004 WHEN 'battery' THEN 0.01 WHEN 'clothes' THEN 0.003
       WHEN 'shoes' THEN 0.003 WHEN 'paper' THEN 0.001 WHEN 'biological' THEN 0.001 ELSE 0.002 END)
    * (CASE WHEN contaminated THEN 0.25 ELSE 1 END) ELSE 0 END AS payout_sol,
  CAST(NULL AS STRING) AS payout_tx_sig
FROM labeled
