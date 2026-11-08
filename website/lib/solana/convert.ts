// Reward amounts are decided in CAD cents by the face API (face_api/app/rewards.py) and converted to SOL only here,
// at the live rate, when the payout is sent.
export const LAMPORTS_PER_SOL = 1_000_000_000;
export const MAX_PAYOUT_CENTS = 100; // sanity bound per interaction (one item pays 5 cents): a bad request can never send more

/** cents (CAD) -> lamports at `cadPerSol`, rounded to the nearest lamport. */
export function centsToLamports(cents: number, cadPerSol: number): number {
  if (!Number.isInteger(cents) || cents <= 0) throw new Error("reward_cents must be a positive whole number");
  if (!Number.isFinite(cadPerSol) || cadPerSol <= 0) throw new Error("invalid SOL/CAD rate");
  return Math.round(((cents / 100) / cadPerSol) * LAMPORTS_PER_SOL);
}

export const lamportsToSol = (lamports: number) => lamports / LAMPORTS_PER_SOL;

export const memoFor = (interactionId: string) => `cashcan:${interactionId}`;

/** Does an RPC `memo` field (e.g. "[25] cashcan:abc" or several joined by "; ") contain exactly this memo? */
export function memoMatches(rpcMemo: string | null | undefined, memo: string): boolean {
  if (!rpcMemo) return false;
  return rpcMemo.split(/;\s*/).map((m) => m.replace(/^\s*\[\d+\]\s*/, "").trim()).includes(memo);
}
