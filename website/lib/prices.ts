// The price catalogue shown on /prices. Edit this one file to change what the site says; amounts are in cents.
// CashCan's cash back is half the BC beverage-container deposit (10¢ on every container type below).
// `null` means "no price set yet" and is shown as such, never as 0.

export type ContainerIcon = "can" | "plastic-bottle" | "plastic-cup" | "drink-box" | "gable-top" | "glass-bottle";

export interface ContainerPrice {
  id: string;
  name: string;
  prep: string; // how to bring it, shown under the name
  size: string;
  depositCents: number; // BC deposit on the container
  icon: ContainerIcon;
  examples: string;
}

export const CASH_BACK_SHARE = 0.5; // CashCan pays half the deposit

export const cashBackCents = (c: ContainerPrice) => Math.round(c.depositCents * CASH_BACK_SHARE * 10) / 10;

export const CONTAINERS: ContainerPrice[] = [
  { id: "aluminum-can", name: "Aluminum Can", prep: "Leave tabs on", size: "0 – 1 L", depositCents: 10, icon: "can",
    examples: "Pop, sparkling water, energy drinks, beer and cider cans." },
  { id: "plastic-bottle", name: "Plastic Bottle", prep: "Caps on, labels on", size: "All sizes", depositCents: 10, icon: "plastic-bottle",
    examples: "Water, pop, juice and sports-drink bottles." },
  { id: "plastic-cup", name: "Plastic Cup", prep: "Polypropylene cup with lid", size: "0 – 454 mL", depositCents: 10, icon: "plastic-cup",
    examples: "Sealed drink cups with a peel-off lid, like fruit or pudding drinks." },
  { id: "drink-box", name: "Drink Box", prep: "Caps on, push the straws in", size: "All sizes", depositCents: 10, icon: "drink-box",
    examples: "Juice boxes and other aseptic drink cartons." },
  { id: "gable-top", name: "Gable Top", prep: "Caps on", size: "All sizes", depositCents: 10, icon: "gable-top",
    examples: "Juice and milk cartons with a peaked top." },
  { id: "glass-bottle", name: "Glass Bottle", prep: "Caps on, labels on", size: "All sizes", depositCents: 10, icon: "glass-bottle",
    examples: "Juice, pop, beer and wine bottles." },
];

export interface OtherPrice {
  id: string;
  name: string;
  bin: "Organics" | "Waste";
  cents: number | null;
  note: string;
}

// Things the bin sorts that are not deposit containers.
export const OTHER: OtherPrice[] = [
  { id: "organics", name: "Food scraps", bin: "Organics", cents: null, note: "Sorted for you into the right bin. A price has not been set yet." },
  { id: "waste", name: "Everything else", bin: "Waste", cents: 0, note: "Goes to Waste. It is sorted and counted, but does not earn a reward." },
];

export const formatCents = (c: number | null) => (c == null ? "Not set yet" : c === 0 ? "No reward" : `${c}¢`);
