// Live SOL price in CAD for the browser (no CORS or rate-limit trouble there). The logic is shared with /api/payout: lib/rateQuote.ts.
import { solCadQuote } from "@/lib/rateQuote";

export const dynamic = "force-dynamic";

export async function GET() {
  const q = await solCadQuote();
  if (!q) return Response.json({ error: "The SOL price is unavailable right now." }, { status: 502 });
  return Response.json(
    { cadPerSol: q.cadPerSol, solPerCad: 1 / q.cadPerSol, source: q.source, fetchedAt: new Date(q.fetchedAt).toISOString() },
    { headers: { "Cache-Control": "public, s-maxage=60, stale-while-revalidate=300" } },
  );
}
