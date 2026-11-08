// Demo data for the dashboard. Labelled "Demo data" in the UI. Replace with real
// per-user detections (backend activity log / Databricks) once drops are linked to accounts.

export type RangeKey = "week" | "today" | "last30";
export type Outcome = "confirmed" | "flagged" | "review";

export const RANGES: Record<RangeKey, {
  label: string; long: string; days: string; total: number; confirmed: number; flagged: number; review: number;
}> = {
  week: { label: "1–7 Nov 2026", long: "1–7 November 2026", days: "7 days", total: 128, confirmed: 104, flagged: 16, review: 8 },
  today: { label: "Today", long: "7 November 2026", days: "today", total: 21, confirmed: 17, flagged: 3, review: 1 },
  last30: { label: "Last 30 days", long: "9 Oct – 7 Nov 2026", days: "30 days", total: 512, confirmed: 401, flagged: 71, review: 40 },
};

export const RANGE_ORDER: RangeKey[] = ["week", "today", "last30"];

export interface Detection {
  id: number;
  icon: "cup" | "box" | "can" | "peel";
  item: string;
  note: string;
  route: string;
  kind: Outcome;
  time: string;
  detail: string;
}

export const DETECTIONS: Detection[] = [
  { id: 1, icon: "cup", item: "Paper cup", note: "Coating uncertain", route: "Hold · check local rules", kind: "review", time: "14:42",
    detail: "Some paper cups have a plastic lining. The front camera couldn't tell, so this one is held until the local rule is checked." },
  { id: 2, icon: "box", item: "Plastic bottle", note: "Headed for the wrong bin", route: "Redirected · Waste → Cans", kind: "flagged", time: "14:38",
    detail: "The cameras saw a recyclable bottle going toward Waste, so the bin lit up the Cans opening instead. One less recyclable lost." },
  { id: 3, icon: "can", item: "Aluminum can", note: "Right bin first time", route: "Cans · sample route", kind: "confirmed", time: "14:31",
    detail: "Top and front cameras agreed (0.94 confidence). Routed to recycling." },
  { id: 4, icon: "peel", item: "Banana peel", note: "Organic item detected", route: "Organics · sample route", kind: "confirmed", time: "14:25",
    detail: "Organic item, routed to organics." },
];

// ---- Items-sorted histogram, split by bin (demo data) ----

export type Category = "cans" | "organics" | "waste";

export const CATEGORIES: { key: Category; label: string; color: string }[] = [
  { key: "cans", label: "Cans & containers", color: "#2F6DB5" },
  { key: "organics", label: "Organics", color: "#3E9B5A" },
  { key: "waste", label: "Waste", color: "#C98A3A" },
];

// SOL paid per reward-eligible container. Mirrors BASE_REWARD_SOL.cans in backend/src/rewardTable.ts
// (a devnet placeholder). Only the cans bin pays.
export const REWARD_PER_CONTAINER_SOL = 0.004;

export interface HistBucket { label: string; cans: number; organics: number; waste: number }

// Deterministic "random" weights so the demo chart looks natural but never changes between renders.
function weights(n: number, seed: number): number[] {
  return Array.from({ length: n }, (_, i) => 1 + 0.35 * Math.sin(i * 1.7 + seed) + 0.2 * Math.cos(i * 0.9 + seed * 2));
}

// Split `total` into integers proportional to `w` (largest remainder), so the buckets add up exactly.
function apportion(total: number, w: number[]): number[] {
  const sum = w.reduce((a, b) => a + b, 0);
  const raw = w.map((x) => (x / sum) * total);
  const out = raw.map(Math.floor);
  const order = raw.map((x, i) => [x - Math.floor(x), i] as const).sort((a, b) => b[0] - a[0]);
  const left = total - out.reduce((a, b) => a + b, 0);
  for (let k = 0; k < left; k++) out[order[k][1]]++;
  return out;
}

function buildHistogram(labels: string[], total: number, seed: number): HistBucket[] {
  return apportion(total, weights(labels.length, seed)).map((n, i) => {
    const [cans, organics, waste] = apportion(n, [0.46 + 0.08 * Math.sin(i + seed), 0.34, 0.2]);
    return { label: labels[i], cans, organics, waste };
  });
}

const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export const HISTOGRAMS: Record<RangeKey, { unit: string; buckets: HistBucket[] }> = {
  // 1 Nov 2026 is a Sunday.
  week: { unit: "per day", buckets: buildHistogram(Array.from({ length: 7 }, (_, i) => `${DAYS[i]} ${i + 1}`), RANGES.week.total, 1) },
  today: { unit: "per hour", buckets: buildHistogram(Array.from({ length: 12 }, (_, i) => `${i + 8}:00`), RANGES.today.total, 2) },
  last30: {
    unit: "per day",
    buckets: buildHistogram(
      Array.from({ length: 30 }, (_, i) => { const d = new Date(Date.UTC(2026, 9, 9 + i)); return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}`; }),
      RANGES.last30.total, 3),
  },
};

export const OUTCOMES:{ key: Outcome; label: string; status: string; color: string }[] = [
  { key: "confirmed", label: "Confirmed", status: "Confirmed", color: "#2D4D3E" },
  { key: "flagged", label: "Redirected", status: "Redirected", color: "#C49A5A" },
  { key: "review", label: "To review", status: "Needs review", color: "#D3D8C8" },
];
