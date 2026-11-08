// The signed-in user's drops, from the face API's GET /me/activity (face_api/app/activity.py). Real stored values only.
import { FACE_API, FaceApiError } from "./faceApi";

export type RangeKey = "today" | "week" | "30d";
export type ItemClass = "cans" | "organics" | "waste";
export type PayoutStatus = "none" | "held" | "pending" | "sending" | "paid" | "failed";

export interface Drop {
  interaction_id: string;
  item_class: ItemClass | string;
  bin_id: string | null;
  bin_name: string | null;
  created_at: string;           // ISO, UTC
  reward_cents: number;
  payout_status: PayoutStatus;
  reason: string | null;        // why there is no reward: not_recognised | low_confidence | not_reward_eligible | cooldown
  lamports: number | null;
  sol: number | null;
  cad_per_sol: number | null;
  tx_signature: string | null;
  payout_error: string | null;
}

export interface Activity {
  range: RangeKey;
  timezone: string;
  start: string;
  unit: "per hour" | "per day";
  totals: {
    items: number; reward_cents: number; paid_count: number; paid_lamports: number; paid_sol: number; paid_cad: number;
    held_count: number; held_cents: number; pending_count: number; pending_cents: number; failed_count: number;
  };
  by_bin: Record<ItemClass, number>;
  series: { label: string; start: string; cans: number; organics: number; waste: number }[];
  recent: Drop[];
}

export async function getActivity(token: string, range: RangeKey): Promise<Activity> {
  const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || "America/Vancouver";
  let res: Response;
  try {
    res = await fetch(`${FACE_API}/me/activity?range=${range}&tz=${encodeURIComponent(tz)}`, { headers: { Authorization: `Bearer ${token}` }, cache: "no-store" });
  } catch {
    throw new FaceApiError("We couldn't reach CashCan. Check your connection and try again.", 0);
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new FaceApiError(typeof body?.detail === "string" ? body.detail : `Your activity couldn't be loaded (${res.status}).`, res.status);
  return body as Activity;
}

export const explorerTx = (sig: string) => `https://explorer.solana.com/tx/${sig}?cluster=devnet`;
export const explorerAddress = (a: string) => `https://explorer.solana.com/address/${a}?cluster=devnet`;
