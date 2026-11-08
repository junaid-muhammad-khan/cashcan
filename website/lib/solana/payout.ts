// One devnet transfer per interaction, tagged with the memo "cashcan:<interaction_id>".
// Idempotent: before sending, the treasury's recent transactions are searched for that memo, and an existing transfer is
// returned instead of sending a second one. The face API's reconcile job uses the same lookup for rows stuck in "sending".
import {
  Connection, Keypair, PublicKey, SystemProgram, Transaction, TransactionInstruction, sendAndConfirmTransaction,
} from "@solana/web3.js";
import { memoFor, memoMatches } from "./convert";

export const MEMO_PROGRAM_ID = new PublicKey("MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr");
const FEE_RESERVE_LAMPORTS = 10_000; // generous: a transfer + memo costs 5,000

export class PayoutError extends Error {
  constructor(message: string, public status: number, public code: string) { super(message); }
}

export function parseWallet(to: unknown): PublicKey {
  if (typeof to !== "string" || !/^[1-9A-HJ-NP-Za-km-z]{32,44}$/.test(to)) throw new PayoutError("`to` is not a Solana wallet address.", 400, "bad_wallet");
  try { return new PublicKey(to); } catch { throw new PayoutError("`to` is not a Solana wallet address.", 400, "bad_wallet"); }
}

export interface Found { signature: string; lamports: number | null }

/** The transfer already sent for this interaction, if any (searches the treasury's latest `depth` transactions). */
export async function findTransfer(conn: Connection, treasury: PublicKey, interactionId: string, depth = 1000): Promise<Found | null> {
  const memo = memoFor(interactionId);
  const sigs = await conn.getSignaturesForAddress(treasury, { limit: depth }, "confirmed");
  const hit = sigs.find((s) => s.err === null && memoMatches(s.memo, memo));
  if (!hit) return null;
  let lamports: number | null = null;
  try {
    const tx = await conn.getParsedTransaction(hit.signature, { commitment: "confirmed", maxSupportedTransactionVersion: 0 });
    for (const ix of tx?.transaction.message.instructions ?? []) {
      if ("parsed" in ix && ix.program === "system" && ix.parsed?.type === "transfer") lamports = Number(ix.parsed.info.lamports);
    }
  } catch { /* the signature is what matters */ }
  return { signature: hit.signature, lamports };
}

export async function sendTransfer(conn: Connection, treasury: Keypair, to: PublicKey, lamports: number, interactionId: string): Promise<string> {
  const balance = await conn.getBalance(treasury.publicKey, "confirmed");
  if (balance < lamports + FEE_RESERVE_LAMPORTS) {
    throw new PayoutError(`Treasury balance too low for this payout (${balance} lamports, needs ${lamports + FEE_RESERVE_LAMPORTS}). Fund the devnet treasury.`, 503, "treasury_low");
  }
  const tx = new Transaction().add(
    SystemProgram.transfer({ fromPubkey: treasury.publicKey, toPubkey: to, lamports }),
    new TransactionInstruction({ programId: MEMO_PROGRAM_ID, keys: [], data: Buffer.from(memoFor(interactionId), "utf8") }),
  );
  return sendAndConfirmTransaction(conn, tx, [treasury], { commitment: "confirmed" });
}
