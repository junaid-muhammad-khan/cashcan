import { randomUUID } from "node:crypto";

// Writes to workspace.cashcan.activity_log via the Databricks SQL Statement
// Execution API (REST + fetch — no extra dependency needed). See the main
// README's "Activity log / dashboard" item.
export interface ActivityLogEvent {
  userId: string;
  itemLabel: string;
  binDecision: string;
  contaminated: boolean;
  contaminationScore?: number;
  classifierConfidence: number;
  topCamLabel?: string;
  frontCamLabel?: string;
  rewardEligible: boolean;
  payoutSol: number;
  payoutTxSig?: string;
}

type SqlParam = { name: string; value: string | null; type: string };

function warehouseIdFromHttpPath(httpPath: string): string {
  return httpPath.split("/").filter(Boolean).pop() ?? "";
}

// Never throws: a Databricks hiccup during a live demo must not block or
// fail the actual payout, which is the part that matters.
export async function logActivity(event: ActivityLogEvent): Promise<void> {
  const host = process.env.DATABRICKS_SERVER_HOSTNAME;
  const httpPath = process.env.DATABRICKS_HTTP_PATH;
  const token = process.env.DATABRICKS_TOKEN;

  if (!host || !httpPath || !token) {
    console.log("Databricks logging skipped: DATABRICKS_SERVER_HOSTNAME / DATABRICKS_HTTP_PATH / DATABRICKS_TOKEN not set in .env");
    return;
  }

  const parameters: SqlParam[] = [
    { name: "event_id", value: randomUUID(), type: "STRING" },
    { name: "user_id", value: event.userId, type: "STRING" },
    { name: "item_label", value: event.itemLabel, type: "STRING" },
    { name: "bin_decision", value: event.binDecision, type: "STRING" },
    { name: "contaminated", value: String(event.contaminated), type: "BOOLEAN" },
    {
      name: "contamination_score",
      value: event.contaminationScore != null ? String(event.contaminationScore) : null,
      type: "DOUBLE",
    },
    { name: "classifier_confidence", value: String(event.classifierConfidence), type: "DOUBLE" },
    { name: "top_cam_label", value: event.topCamLabel ?? null, type: "STRING" },
    { name: "front_cam_label", value: event.frontCamLabel ?? null, type: "STRING" },
    { name: "reward_eligible", value: String(event.rewardEligible), type: "BOOLEAN" },
    { name: "payout_sol", value: String(event.payoutSol), type: "DOUBLE" },
    { name: "payout_tx_sig", value: event.payoutTxSig ?? null, type: "STRING" },
  ];

  const statement = `
    INSERT INTO workspace.cashcan.activity_log
      (event_id, ts, user_id, item_label, bin_decision, contaminated, contamination_score,
       classifier_confidence, top_cam_label, front_cam_label, reward_eligible, payout_sol, payout_tx_sig)
    VALUES
      (:event_id, current_timestamp(), :user_id, :item_label, :bin_decision, :contaminated, :contamination_score,
       :classifier_confidence, :top_cam_label, :front_cam_label, :reward_eligible, :payout_sol, :payout_tx_sig)
  `;

  try {
    const res = await fetch(`https://${host}/api/2.0/sql/statements`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        warehouse_id: warehouseIdFromHttpPath(httpPath),
        statement,
        parameters,
        wait_timeout: "30s",
      }),
    });

    if (!res.ok) {
      console.log(`Databricks activity log insert failed (${res.status}): ${await res.text()}`);
      return;
    }

    const body = await res.json();
    if (body.status?.state && body.status.state !== "SUCCEEDED") {
      console.log(`Databricks activity log insert did not succeed: ${JSON.stringify(body.status)}`);
    }
  } catch (err) {
    console.log(`Databricks activity log insert failed: ${err instanceof Error ? err.message : String(err)}`);
  }
}
