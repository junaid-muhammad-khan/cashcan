// Base reward per item class, keyed to the 3 physical bins the classifier actually
// outputs (ml/class_map.yaml: "cans" | "organics" | "waste" — see predict.py's "bin"
// field). Amounts are hackathon placeholders (devnet SOL has no real value) — swap for
// the team's real per-item figures once decided (README "Open questions").
export const BASE_REWARD_SOL: Record<string, number> = {
  // "Cans" = BC Return-It deposit-refund containers (metal/plastic/glass) — the one
  // bucket class_map.yaml ties to the reward/payout mechanic.
  cans: 0.004,
  // Not a deposit-refund item; no reward until the team decides otherwise.
  organics: 0,
  // Catch-all / non-eligible per class_map.yaml ("reward_eligible=false, bin never
  // physically actuated for it").
  waste: 0,
};

// Reward-eligible item, contaminated: reduced payout rather than zero, so the
// bin still has some incentive to sort (even if imperfectly) instead of none.
const CONTAMINATED_MULTIPLIER = 0.25;

export interface RewardInput {
  itemClass: string;
  contaminated: boolean;
  confidence: number; // 0..1
}

export function computeRewardSol(input: RewardInput, minConfidence: number): number {
  const base = BASE_REWARD_SOL[input.itemClass];
  if (base === undefined || base <= 0) return 0;
  if (input.confidence < minConfidence) return 0;

  return input.contaminated ? base * CONTAMINATED_MULTIPLIER : base;
}
