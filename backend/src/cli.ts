import "dotenv/config";
import { Command } from "commander";
import { LAMPORTS_PER_SOL } from "@solana/web3.js";
import { getConnection, loadOrCreateTreasury, airdropIfLow } from "./treasury.js";
import { computeRewardSol } from "./rewardTable.js";
import { payUser, PayoutRejected } from "./payout.js";
import { logActivity } from "./activityLog.js";

const program = new Command();
const minConfidence = Number(process.env.MIN_CONFIDENCE ?? "0.75");
const cooldownSeconds = Number(process.env.PAYOUT_COOLDOWN_SECONDS ?? "30");

program
  .command("init-treasury")
  .description("Generate (if needed) the treasury wallet and fund it from the devnet faucet")
  .action(async () => {
    const connection = getConnection();
    const treasury = loadOrCreateTreasury();
    console.log(`Treasury pubkey: ${treasury.publicKey.toBase58()}`);

    let balance: number;
    try {
      balance = await airdropIfLow(connection, treasury);
    } catch (err) {
      console.log("Automated faucet request failed (Solana's RPC faucet is closed).");
      console.log(`Fund this wallet manually at https://faucet.solana.com using the pubkey above.`);
      balance = await connection.getBalance(treasury.publicKey);
    }
    console.log(`Balance: ${balance / LAMPORTS_PER_SOL} SOL`);
  });

program
  .command("balance")
  .description("Print the treasury wallet's current devnet balance")
  .action(async () => {
    const connection = getConnection();
    const treasury = loadOrCreateTreasury();
    const balance = await connection.getBalance(treasury.publicKey);
    console.log(`Treasury pubkey: ${treasury.publicKey.toBase58()}`);
    console.log(`Balance: ${balance / LAMPORTS_PER_SOL} SOL`);
  });

program
  .command("payout")
  .description("Simulate a reward payout for one classified item")
  .requiredOption("--user <pubkey>", "recipient's Solana wallet address")
  .requiredOption("--item <class>", "item class, e.g. cardboard, glass, metal")
  .option("--contaminated", "mark the item as contaminated", false)
  .option("--confidence <0-1>", "classifier confidence", "1.0")
  .option("--dry-run", "build and validate the payout but never hit the network", false)
  .action(async (opts) => {
    const connection = getConnection();
    const treasury = loadOrCreateTreasury();

    const contaminated = Boolean(opts.contaminated);
    const confidence = Number(opts.confidence);
    const rewardSol = computeRewardSol(
      {
        itemClass: opts.item,
        contaminated,
        confidence,
      },
      minConfidence,
    );

    // No local rule-lookup table exists yet (see main README "Open questions"),
    // so bin_decision just echoes the classified item for now.
    const activityBase = {
      userId: opts.user,
      itemLabel: opts.item,
      binDecision: opts.item,
      contaminated,
      classifierConfidence: confidence,
    };

    try {
      const result = await payUser(
        connection,
        treasury,
        opts.user,
        rewardSol,
        cooldownSeconds,
        Boolean(opts.dryRun),
      );
      if (opts.dryRun) {
        console.log(result);
        return;
      }
      console.log(`Paid ${rewardSol} SOL to ${opts.user}`);
      console.log(`Signature: ${result}`);
      const cluster = process.env.SOLANA_CLUSTER ?? "devnet";
      if (cluster === "localnet") {
        console.log("Running on a local validator — not visible on the public Explorer.");
        console.log(`Verify with: solana confirm ${result} --url http://127.0.0.1:8899`);
      } else {
        console.log(`Explorer: https://explorer.solana.com/tx/${result}?cluster=${cluster}`);
      }
      await logActivity({ ...activityBase, rewardEligible: true, payoutSol: rewardSol, payoutTxSig: result });
    } catch (err) {
      if (err instanceof PayoutRejected) {
        console.log(`No payout: ${err.message}`);
        if (!opts.dryRun) {
          await logActivity({ ...activityBase, rewardEligible: false, payoutSol: 0 });
        }
        return;
      }
      throw err;
    }
  });

program.parseAsync(process.argv);
