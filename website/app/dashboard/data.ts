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
  { id: 2, icon: "box", item: "Takeout container", note: "Food residue detected", route: "Pause · remove residue", kind: "flagged", time: "14:38",
    detail: "Both cameras saw food residue. Scrape or rinse it, then drop it again for a clean sort." },
  { id: 3, icon: "can", item: "Aluminum can", note: "No residue flagged", route: "Recycling · sample route", kind: "confirmed", time: "14:31",
    detail: "Top and front cameras agreed (0.94 confidence). Routed to recycling." },
  { id: 4, icon: "peel", item: "Banana peel", note: "Organic item detected", route: "Organics · sample route", kind: "confirmed", time: "14:25",
    detail: "Organic item, routed to organics. No contamination check needed." },
];

export const OUTCOMES: { key: Outcome; label: string; status: string; color: string }[] = [
  { key: "confirmed", label: "Confirmed", status: "Confirmed", color: "#2D4D3E" },
  { key: "flagged", label: "Flagged", status: "Flagged", color: "#C49A5A" },
  { key: "review", label: "To review", status: "Needs review", color: "#D3D8C8" },
];
