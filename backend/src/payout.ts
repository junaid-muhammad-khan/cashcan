import { readFileSync, writeFileSync, existsSync } from "node:fs";
import {
  Connection,
  Keypair,
  PublicKey,
  SystemProgram,
  Transaction,
  sendAndConfirmTransaction,
  LAMPORTS_PER_SOL,
} from "@solana/web3.js";

// Per-user cooldown so one person can't drain the treasury by feeding items
// through quickly (README anti-abuse: "rate limit per user per time window").
// Persisted to disk, not kept in memory: each scan is expected to invoke this
// as a fresh process (CLI today, a hardware-triggered script later), so an
// in-memory Map would silently reset on every call and never actually block
// anything.
const COOLDOWN_PATH = new URL("../payout-cooldowns.json", import.meta.url).pathname;

function loadCooldowns(): Record<string, number> {
  if (!existsSync(COOLDOWN_PATH)) return {};
  return JSON.parse(readFileSync(COOLDOWN_PATH, "utf-8"));
}

function saveCooldowns(cooldowns: Record<string, number>): void {
  writeFileSync(COOLDOWN_PATH, JSON.stringify(cooldowns));
}

export class PayoutRejected extends Error {}

export async function payUser(
  connection: Connection,
  treasury: Keypair,
  userPubkeyStr: string,
  rewardSol: number,
  cooldownSeconds: number,
  dryRun = false,
): Promise<string> {
  if (rewardSol <= 0) {
    throw new PayoutRejected("reward is zero (below confidence threshold, contaminated, or non-eligible item)");
  }

  const now = Date.now();
  const cooldowns = loadCooldowns();
  const last = cooldowns[userPubkeyStr] ?? 0;
  if (now - last < cooldownSeconds * 1000) {
    const remaining = Math.ceil((cooldownSeconds * 1000 - (now - last)) / 1000);
    throw new PayoutRejected(`user is in cooldown (${remaining}s remaining of ${cooldownSeconds}s)`);
  }

  let userPubkey: PublicKey;
  try {
    userPubkey = new PublicKey(userPubkeyStr);
  } catch {
    throw new PayoutRejected(`"${userPubkeyStr}" is not a valid Solana wallet address`);
  }
  const lamports = Math.round(rewardSol * LAMPORTS_PER_SOL);

  if (dryRun) {
    // Skip the network call (and the cooldown write) so a dry run never needs
    // a funded treasury and never blocks a later real payout.
    return `DRY RUN: would transfer ${lamports} lamports (${rewardSol} SOL) from treasury ${treasury.publicKey.toBase58()} to ${userPubkeyStr}`;
  }

  const transaction = new Transaction().add(
    SystemProgram.transfer({
      fromPubkey: treasury.publicKey,
      toPubkey: userPubkey,
      lamports,
    }),
  );

  const signature = await sendAndConfirmTransaction(connection, transaction, [treasury]);
  cooldowns[userPubkeyStr] = now;
  saveCooldowns(cooldowns);
  return signature;
}
