// Reward payouts (devnet, or simulated in demo mode). Called only by the face API; see lib/payoutHandler.ts.
import { handleGet, handlePost, type Deps } from "@/lib/payoutHandler";
import { solCadQuote } from "@/lib/rateQuote";
import { getConnection, loadTreasury } from "@/lib/solana/treasury";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
// Short on purpose: a transaction's blockhash is fetched within this window, so a send that is still unknown after the face
// API's PAYOUT_STUCK_SECONDS (180 s) has expired on chain and can be safely retried.
export const maxDuration = 30;

const deps = (): Deps => ({
  secret: process.env.PAYOUT_SECRET,
  connection: getConnection,
  treasury: loadTreasury,
  quote: () => solCadQuote(30_000),
  // PAYOUT_MODE=devnet sends real devnet transfers; PAYOUT_MODE=demo never does. Unset: devnet only if a treasury key exists.
  mode: process.env.PAYOUT_MODE === "demo" || (process.env.PAYOUT_MODE !== "devnet" && !process.env.TREASURY_SECRET_KEY) ? "demo" : "devnet",
});

export const POST = (req: Request) => handlePost(req, deps());
export const GET = (req: Request) => handleGet(req, deps());
