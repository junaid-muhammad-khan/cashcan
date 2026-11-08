import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { Connection, Keypair, clusterApiUrl, LAMPORTS_PER_SOL } from "@solana/web3.js";
import bs58 from "bs58";

const KEYPAIR_PATH = new URL("../treasury-keypair.json", import.meta.url).pathname;

export function getConnection(): Connection {
  const cluster = process.env.SOLANA_CLUSTER ?? "devnet";
  if (cluster === "localnet") {
    // solana-test-validator's default RPC endpoint — unlimited, instant airdrops,
    // no dependency on the public devnet faucet (useful for a live demo).
    return new Connection("http://127.0.0.1:8899", "confirmed");
  }
  return new Connection(clusterApiUrl(cluster as "devnet" | "testnet" | "mainnet-beta"), "confirmed");
}

export function loadOrCreateTreasury(): Keypair {
  const envKey = process.env.TREASURY_SECRET_KEY;
  if (envKey) {
    return Keypair.fromSecretKey(bs58.decode(envKey));
  }

  if (existsSync(KEYPAIR_PATH)) {
    const raw = JSON.parse(readFileSync(KEYPAIR_PATH, "utf-8"));
    return Keypair.fromSecretKey(Uint8Array.from(raw));
  }

  const keypair = Keypair.generate();
  writeFileSync(KEYPAIR_PATH, JSON.stringify(Array.from(keypair.secretKey)));
  return keypair;
}

export async function airdropIfLow(
  connection: Connection,
  keypair: Keypair,
  minSol = 1,
  airdropSol = 2,
): Promise<number> {
  const balance = await connection.getBalance(keypair.publicKey);
  if (balance >= minSol * LAMPORTS_PER_SOL) {
    return balance;
  }

  const signature = await connection.requestAirdrop(keypair.publicKey, airdropSol * LAMPORTS_PER_SOL);
  await connection.confirmTransaction(signature, "confirmed");
  return connection.getBalance(keypair.publicKey);
}
