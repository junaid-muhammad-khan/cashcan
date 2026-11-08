// Rules and pure helpers for the kids' sorting game ("Sort It!", /play). No React in here so it can be unit tested.
// The scoring constants mirror face_api/app/game.py: the server recomputes every score, so keep the two in step.

export type BinId = "cans" | "organics" | "waste";

export interface Bin {
  id: BinId;
  name: string;      // what kids see on the bin
  hint: string;      // one line under the name on the how-to-play screen
  color: string;
  dark: string;
}

// The same three bins as the real CashCan bin (cans = BC Return-It deposit containers).
export const BINS: Bin[] = [
  { id: "cans", name: "Cans & bottles", hint: "Drink cans, bottles and cartons", color: "#2BB673", dark: "#157A46" },
  { id: "organics", name: "Food scraps", hint: "Leftover food and peels", color: "#E3B23C", dark: "#A06E00" },
  { id: "waste", name: "Garbage", hint: "Wrappers, bags and plastic bits", color: "#9AA6A0", dark: "#5C6B62" },
];

export const BIN_NAME: Record<BinId, string> = { cans: "Cans & bottles", organics: "Food scraps", waste: "Garbage" };

export type ArtId =
  | "can" | "plastic-bottle" | "drink-box" | "gable-top" | "glass-bottle"
  | "banana" | "apple-core" | "burger" | "fries"
  | "chip-bag" | "candy" | "cup-straw" | "fork";

export interface Item {
  id: ArtId;
  name: string;
  bin: BinId;
  easy: boolean;   // shown from level 1; the rest join at level 2
}

export const ITEMS: Item[] = [
  { id: "can", name: "Soda can", bin: "cans", easy: true },
  { id: "plastic-bottle", name: "Water bottle", bin: "cans", easy: true },
  { id: "drink-box", name: "Juice box", bin: "cans", easy: false },
  { id: "gable-top", name: "Milk carton", bin: "cans", easy: false },
  { id: "glass-bottle", name: "Glass bottle", bin: "cans", easy: false },
  { id: "banana", name: "Banana peel", bin: "organics", easy: true },
  { id: "burger", name: "Burger", bin: "organics", easy: true },
  { id: "apple-core", name: "Apple core", bin: "organics", easy: false },
  { id: "fries", name: "Fries", bin: "organics", easy: false },
  { id: "chip-bag", name: "Chip bag", bin: "waste", easy: true },
  { id: "candy", name: "Candy wrapper", bin: "waste", easy: true },
  { id: "cup-straw", name: "Cup with straw", bin: "waste", easy: false },
  { id: "fork", name: "Plastic fork", bin: "waste", easy: false },
];

// ---- rules (mirrors face_api/app/game.py)
export const LIVES = 3;
export const POINTS_PER_ITEM = 10;
export const POINTS_PER_STREAK_ITEM = 5;
export const ITEMS_PER_LEVEL = 8;
export const STREAK_CHEER_EVERY = 5;

export const scoreOf = (correct: number, bestStreak: number) => correct * POINTS_PER_ITEM + bestStreak * POINTS_PER_STREAK_ITEM;
export const levelOf = (correct: number) => 1 + Math.floor(correct / ITEMS_PER_LEVEL);
export const accuracyOf = (correct: number, wrong: number, spilled: number) => {
  const total = correct + wrong + spilled;
  return total ? Math.round((100 * correct) / total) : 0;
};

/** How long a kid has to sort one item before it spills: 7 s at level 1, half a second less each level, never under 2.8 s. */
export const timeForLevel = (level: number) => Math.max(2800, 7000 - (level - 1) * 500);

export const binOf = (id: BinId) => BINS.find((b) => b.id === id)!;

/**
 * The next item to show. Picks a bin first (so the three bins come up about equally often), then an item for it,
 * skipping anything shown in the last two turns. Level 1 only uses the easy items.
 */
export function nextItem(level: number, recent: ArtId[], rng: () => number = Math.random): Item {
  const pool = ITEMS.filter((i) => level > 1 || i.easy);
  const bin = BINS[Math.floor(rng() * BINS.length)].id;
  const fresh = pool.filter((i) => i.bin === bin && !recent.slice(-2).includes(i.id));
  const choices = fresh.length ? fresh : pool.filter((i) => i.bin === bin);
  return choices[Math.floor(rng() * choices.length)];
}

export interface GameResult {
  game_id: string;
  correct: number;
  wrong: number;
  spilled: number;
  best_streak: number;
  duration_ms: number;
}

export const newGameId = () =>
  (typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `g-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`);

/** What to tell a child after a mistake: kind, and says where it really goes. */
export function lessonFor(item: Item, how: "wrong" | "spill"): string {
  const where = BIN_NAME[item.bin];
  return how === "spill" ? `Oh no, it spilled! ${item.name} goes in ${where}.` : `Oops! ${item.name} goes in ${where}.`;
}

export const CHEERS = ["Great sort!", "Nice one!", "You got it!", "Super!", "Yes!", "Awesome!"];
