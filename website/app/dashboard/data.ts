// DEMO data for the dev-only /dashboard?preview=1 (never shown on the live site). Same shape as GET /me/activity, so the
// preview exercises exactly the code path real data takes. Numbers are invented.
import type { Activity, Drop, ItemClass, RangeKey } from "@/lib/activity";

export const CATEGORIES: { key: ItemClass; label: string; color: string }[] = [
  { key: "cans", label: "Cans & containers", color: "#2F6DB5" },
  { key: "organics", label: "Organics", color: "#3E9B5A" },
  { key: "waste", label: "Waste", color: "#C98A3A" },
];

export const RANGE_LABELS: Record<RangeKey, string> = { today: "Today", week: "Last 7 days", "30d": "Last 30 days" };
export const RANGE_ORDER: RangeKey[] = ["week", "today", "30d"];

const RATE = 126.5;

function demoDrops(now: Date): Drop[] {
  const mk = (i: number, cls: ItemClass, minutesAgo: number, status: Drop["payout_status"], reason: string | null = null): Drop => {
    const cents = status === "none" ? 0 : 5;
    const lamports = status === "paid" ? Math.round((0.05 / RATE) * 1e9) : null;
    return { interaction_id: `demo-${i}`, item_class: cls, bin_id: "bin-1", bin_name: "Demo bin", created_at: new Date(now.getTime() - minutesAgo * 60_000).toISOString(),
      reward_cents: cents, payout_status: status, reason, lamports, sol: lamports && lamports / 1e9, cad_per_sol: lamports ? RATE : null,
      tx_signature: null, payout_error: null };
  };
  return [mk(1, "cans", 4, "paid"), mk(2, "organics", 9, "none", "not_reward_eligible"), mk(3, "cans", 30, "held"),
          mk(4, "cans", 32, "none", "cooldown"), mk(5, "waste", 60, "none", "not_reward_eligible"), mk(6, "cans", 95, "sending")];
}

export function demoActivity(range: RangeKey): Activity {
  const now = new Date();
  const n = range === "today" ? 24 : range === "week" ? 7 : 30;
  const series = Array.from({ length: n }, (_, i) => {
    const w = 1 + 0.35 * Math.sin(i * 1.7) + 0.2 * Math.cos(i * 0.9);
    const label = range === "today" ? `${i}:00` : new Date(now.getTime() - (n - 1 - i) * 86_400_000).toLocaleDateString("en-CA", { day: "numeric", month: "short" });
    return { label, start: "", cans: Math.round(3 * w), organics: Math.round(2 * w), waste: Math.round(1.2 * w) };
  });
  const by = { cans: 0, organics: 0, waste: 0 };
  for (const b of series) { by.cans += b.cans; by.organics += b.organics; by.waste += b.waste; }
  const paid = Math.max(0, by.cans - 3), lam = Math.round((0.05 / RATE) * 1e9);
  return {
    range, timezone: "America/Vancouver", start: now.toISOString(), unit: range === "today" ? "per hour" : "per day",
    totals: { items: by.cans + by.organics + by.waste, reward_cents: (paid + 2) * 5, paid_count: paid, paid_lamports: paid * lam,
      paid_sol: (paid * lam) / 1e9, paid_cad: paid * 0.05, held_count: 1, held_cents: 5, pending_count: 1, pending_cents: 5, failed_count: 0 },
    by_bin: by, series, recent: demoDrops(now),
  };
}
