// POST /api/payout and GET /api/payout, called only by the face API (shared secret PAYOUT_SECRET).
//   POST {interaction_id, to, reward_cents} -> live SOL/CAD rate -> lamports -> devnet transfer with memo "cashcan:<id>"
//        -> {signature, lamports, cad_per_sol, rate_source}. Idempotent: an existing transfer with that memo is returned instead.
//   GET  ?interaction_id=... -> {found, signature, lamports} (used by the reconcile job for rows stuck in "sending").
// Kept out of the route file so tests can pass in a fake connection, treasury and rate.
import type { Connection, Keypair } from "@solana/web3.js";
import { centsToLamports, MAX_PAYOUT_CENTS } from "./solana/convert";
import { PayoutError, findTransfer, parseWallet, sendTransfer } from "./solana/payout";
import type { Quote } from "./rateQuote";
import { bearerMatches } from "./secret";

export interface Deps {
  secret: string | undefined;
  connection: () => Connection;
  treasury: () => Keypair;
  quote: () => Promise<Quote | null>;
  find?: typeof findTransfer;
  send?: typeof sendTransfer;
}

const ID_RE = /^[A-Za-z0-9_.:-]{1,128}$/;
const json = (body: unknown, status = 200) => Response.json(body, { status, headers: { "Cache-Control": "no-store" } });
const fail = (error: string, status: number, code: string) => json({ error, code }, status);

function guard(req: Request, deps: Deps): Response | null {
  if (!deps.secret) return fail("Payouts are not configured (PAYOUT_SECRET).", 503, "not_configured");
  if (!bearerMatches(req.headers.get("authorization"), deps.secret)) return fail("Unauthorized.", 401, "unauthorized");
  return null;
}

function errorResponse(e: unknown): Response {
  if (e instanceof PayoutError) return fail(e.message, e.status, e.code);
  const msg = e instanceof Error ? e.message : String(e);
  console.error("payout error:", msg.slice(0, 300)); // never the key or the request
  return fail(`Payout failed: ${msg.slice(0, 200)}`, 502, "send_failed");
}

export async function handlePost(req: Request, deps: Deps): Promise<Response> {
  const denied = guard(req, deps);
  if (denied) return denied;
  let body: { interaction_id?: unknown; to?: unknown; reward_cents?: unknown };
  try { body = await req.json(); } catch { return fail("Body must be JSON.", 400, "bad_request"); }
  const id = body.interaction_id, cents = body.reward_cents;
  if (typeof id !== "string" || !ID_RE.test(id)) return fail("`interaction_id` is missing or invalid.", 400, "bad_request");
  if (typeof cents !== "number" || !Number.isInteger(cents) || cents <= 0 || cents > MAX_PAYOUT_CENTS)
    return fail(`\`reward_cents\` must be a whole number from 1 to ${MAX_PAYOUT_CENTS}.`, 400, "bad_request");
  try {
    const to = parseWallet(body.to);
    const conn = deps.connection(), treasury = deps.treasury();
    const already = await (deps.find ?? findTransfer)(conn, treasury.publicKey, id);
    const q = await deps.quote();
    if (already) { // sent before (the earlier response was lost): report that transfer, never send a second one
      return json({ signature: already.signature, lamports: already.lamports, cad_per_sol: q?.cadPerSol ?? null,
                    rate_source: q?.source ?? null, duplicate: true });
    }
    if (!q) return fail("The SOL price is unavailable right now; try again shortly.", 503, "rate_unavailable");
    const lamports = centsToLamports(cents, q.cadPerSol);
    const signature = await (deps.send ?? sendTransfer)(conn, treasury, to, lamports, id);
    return json({ signature, lamports, cad_per_sol: q.cadPerSol, rate_source: q.source, duplicate: false });
  } catch (e) {
    return errorResponse(e);
  }
}

export async function handleGet(req: Request, deps: Deps): Promise<Response> {
  const denied = guard(req, deps);
  if (denied) return denied;
  const id = new URL(req.url).searchParams.get("interaction_id");
  if (!id || !ID_RE.test(id)) return fail("`interaction_id` is missing or invalid.", 400, "bad_request");
  try {
    const found = await (deps.find ?? findTransfer)(deps.connection(), deps.treasury().publicKey, id);
    return json(found ? { found: true, ...found } : { found: false });
  } catch (e) {
    return errorResponse(e);
  }
}
