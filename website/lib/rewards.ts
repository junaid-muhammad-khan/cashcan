// The reward table, owned by the face API (face_api/app/rewards.py, GET /face-api/rewards). Read on the server and cached
// for a few minutes. lib/prices.ts is only the fallback when the API can't be reached; face_api/tests/test_payouts.py fails
// if the two disagree. Every container type on /prices is the classifier's "cans" class.
import { CASH_BACK_SHARE, CONTAINERS, OTHER } from "./prices";

export interface RewardTable {
  currency: string;
  deposit_cents: number;
  cash_back_share: number;
  classes: Record<string, number>; // cents per classifier class: cans / organics / waste
}

export const FALLBACK: RewardTable = {
  currency: "CAD",
  deposit_cents: CONTAINERS[0].depositCents,
  cash_back_share: CASH_BACK_SHARE,
  classes: {
    cans: Math.round(CONTAINERS[0].depositCents * CASH_BACK_SHARE),
    organics: OTHER.find((o) => o.id === "organics")?.cents ?? 0,
    waste: OTHER.find((o) => o.id === "waste")?.cents ?? 0,
  },
};

function apiBase(): string | null {
  if (process.env.FACE_API_ORIGIN) return process.env.FACE_API_ORIGIN.replace(/\/$/, ""); // local dev
  const host = process.env.VERCEL_PROJECT_PRODUCTION_URL || process.env.VERCEL_URL;
  return host ? `https://${host}/face-api` : null;
}

export async function getRewardTable(): Promise<{ table: RewardTable; live: boolean }> {
  const base = apiBase();
  if (!base) return { table: FALLBACK, live: false };
  try {
    const res = await fetch(`${base}/rewards`, { next: { revalidate: 300 }, signal: AbortSignal.timeout(3000) });
    if (!res.ok) throw new Error(String(res.status));
    const t = (await res.json()) as RewardTable;
    if (typeof t?.classes?.cans !== "number") throw new Error("bad table");
    return { table: t, live: true };
  } catch {
    return { table: FALLBACK, live: false };
  }
}
