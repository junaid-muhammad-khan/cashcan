import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { Connection, Keypair } from "@solana/web3.js";
import bs58 from "bs58";

// Local operator copy of the treasury key (gitignored). Production reads TREASURY_SECRET_KEY from Vercel instead.
export const KEYPAIR_PATH = new URL("../treasury-keypair.json", import.meta.url).pathname;

export function getConnection(): Connection {
  const url = process.env.SOLANA_RPC_URL || "https://api.devnet.solana.com";
  if (/mainnet/i.test(url)) throw new Error("SOLANA_RPC_URL points at mainnet; CashCan only pays on devnet.");
  return new Connection(url, "confirmed");
}

/** TREASURY_SECRET_KEY (base58) if set, else the local file; with create=true a new key is generated into the file. */
export function loadTreasury(create = false): Keypair {
  const envKey = process.env.TREASURY_SECRET_KEY;
  if (envKey) return Keypair.fromSecretKey(bs58.decode(envKey.trim()));
  if (existsSync(KEYPAIR_PATH)) return Keypair.fromSecretKey(Uint8Array.from(JSON.parse(readFileSync(KEYPAIR_PATH, "utf-8"))));
  if (!create) throw new Error("No treasury key: set TREASURY_SECRET_KEY or run `npm run init-treasury`.");
  const keypair = Keypair.generate();
  writeFileSync(KEYPAIR_PATH, JSON.stringify(Array.from(keypair.secretKey)), { mode: 0o600 });
  return keypair;
}

export const secretBase58 = (k: Keypair) => bs58.encode(k.secretKey);
