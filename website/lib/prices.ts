// The price catalogue shown on /prices. Edit this one file to change what the site says; amounts are in cents.
// Only `cents` is a price. `null` means "no price set yet" and is shown as such, never as 0.
export interface PriceItem {
  id: string;
  name: string;
  bin: "Cans" | "Organics" | "Waste";
  cents: number | null;
  note: string;
}

export const PRICES: PriceItem[] = [
  { id: "can", name: "Can", bin: "Cans", cents: 10, note: "Aluminum drink cans. Rinse first for the full reward." },
  { id: "bottle", name: "Bottle", bin: "Cans", cents: 3, note: "Drink bottles that take a deposit. Empty and rinse first." },
  { id: "organics", name: "Food scraps", bin: "Organics", cents: null, note: "Sorted for you into the right bin. A price has not been set yet." },
  { id: "waste", name: "Everything else", bin: "Waste", cents: 0, note: "Goes to Waste. It is sorted and counted, but does not earn a reward." },
];

export const formatCents = (c: number | null) => (c == null ? "Not set yet" : c === 0 ? "No reward" : `${c}¢`);
