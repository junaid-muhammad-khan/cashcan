// Server-only. The treasury keypair comes from TREASURY_SECRET_KEY (base58, a Vercel environment variable), never from a file.
// Devnet only: a mainnet RPC URL is refused.
import { Connection, Keypair } from "@solana/web3.js";
import bs58 from "bs58";

export const DEFAULT_RPC = "https://api.devnet.solana.com";

export function rpcUrl(): string {
  const url = process.env.SOLANA_RPC_URL || DEFAULT_RPC;
  if (/mainnet/i.test(url)) throw new Error("SOLANA_RPC_URL points at mainnet; CashCan only pays on devnet.");
  return url;
}

export function getConnection(): Connection {
  return new Connection(rpcUrl(), "confirmed");
}

let treasury: Keypair | null = null;

export function loadTreasury(): Keypair {
  if (treasury) return treasury;
  const key = process.env.TREASURY_SECRET_KEY;
  if (!key) throw new Error("TREASURY_SECRET_KEY is not set.");
  treasury = Keypair.fromSecretKey(bs58.decode(key.trim()));
  return treasury;
}
