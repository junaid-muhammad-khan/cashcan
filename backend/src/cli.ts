// Operator tools for the devnet treasury. Payouts themselves are NOT made here any more: the face API decides the reward
// (face_api/app/rewards.py) and the website's Node route sends it (website/app/api/payout, website/lib/solana/).
import "dotenv/config";
import { Command } from "commander";
import { LAMPORTS_PER_SOL } from "@solana/web3.js";
import { KEYPAIR_PATH, getConnection, loadTreasury, secretBase58 } from "./treasury.js";

const program = new Command();

program
  .command("init-treasury")
  .description("Create the treasury key (if there is none) and show its address and devnet balance")
  .action(async () => {
    const t = loadTreasury(true);
    const balance = await getConnection().getBalance(t.publicKey);
    console.log(`Treasury: ${t.publicKey.toBase58()}`);
    console.log(`Balance:  ${balance / LAMPORTS_PER_SOL} SOL (devnet)`);
    if (!process.env.TREASURY_SECRET_KEY) console.log(`Key file: ${KEYPAIR_PATH} (gitignored, never commit it)`);
    console.log("Fund it with devnet SOL at https://faucet.solana.com (a person has to do this; the RPC faucet is closed).");
    console.log("Then put the key in Vercel: `npm run cli -- export-secret` prints the value for TREASURY_SECRET_KEY.");
  });

program
  .command("balance")
  .description("Print the treasury's devnet balance")
  .action(async () => {
    const t = loadTreasury();
    const balance = await getConnection().getBalance(t.publicKey);
    console.log(`Treasury: ${t.publicKey.toBase58()}\nBalance:  ${balance / LAMPORTS_PER_SOL} SOL (devnet)`);
  });

program
  .command("export-secret")
  .description("Print the treasury secret key in base58, for the TREASURY_SECRET_KEY environment variable (keep it private)")
  .action(() => { process.stdout.write(secretBase58(loadTreasury()) + "\n"); });

program
  .command("test-payout")
  .description("Ask the website's /api/payout to pay one test interaction (PAYOUT_URL + PAYOUT_SECRET)")
  .requiredOption("--to <wallet>", "recipient's devnet wallet")
  .option("--cents <n>", "reward in CAD cents", "5")
  .option("--id <interaction_id>", "interaction id (memo cashcan:<id>); reuse it to see the idempotent answer", `cli-${Date.now()}`)
  .action(async (opts) => {
    const url = process.env.PAYOUT_URL, secret = process.env.PAYOUT_SECRET;
    if (!url || !secret) throw new Error("Set PAYOUT_URL and PAYOUT_SECRET.");
    const res = await fetch(url, { method: "POST", headers: { Authorization: `Bearer ${secret}`, "Content-Type": "application/json" },
      body: JSON.stringify({ interaction_id: opts.id, to: opts.to, reward_cents: Number(opts.cents) }) });
    const body = await res.json();
    console.log(res.status, body);
    if (body.signature) console.log(`Explorer: https://explorer.solana.com/tx/${body.signature}?cluster=devnet`);
  });

program.parseAsync(process.argv);
