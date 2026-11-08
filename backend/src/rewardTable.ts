// Base reward per item class, keyed to the unified classes in ml/class_map.yaml.
// Amounts are hackathon placeholders (devnet SOL has no real value) — swap for
// the team's real per-item figures once decided (README "Open questions").
export const BASE_REWARD_SOL: Record<string, number> = {
  cardboard: 0.002,
  glass: 0.002,
  metal: 0.004,
  paper: 0.001,
  plastic: 0.002,
  battery: 0.01,
  clothes: 0.003,
  shoes: 0.003,
  biological: 0.001,
  trash: 0, // catch-all / non-eligible per README reward table
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
