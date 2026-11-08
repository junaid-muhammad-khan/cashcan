// Live SOL price in CAD, read on the server so the browser has no CORS or rate-limit trouble and the page can cache it.
// Tries Coinbase, then CoinGecko, then Kraken (all public, no key). Cached 60 s per server instance and by the CDN.
export const dynamic = "force-dynamic";

type Quote = { cadPerSol: number; source: string };

const SOURCES: [string, () => Promise<number>][] = [
  ["Coinbase", async () => Number((await getJson("https://api.coinbase.com/v2/prices/SOL-CAD/spot")).data.amount)],
  ["CoinGecko", async () => Number((await getJson("https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=cad")).solana.cad)],
  ["Kraken", async () => Number((Object.values((await getJson("https://api.kraken.com/0/public/Ticker?pair=SOLCAD")).result)[0] as { c: string[] }).c[0])],
];

async function getJson(url: string) {
  const res = await fetch(url, { cache: "no-store", signal: AbortSignal.timeout(4000) });
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json();
}

let cache: { at: number; quote: Quote } | null = null;

async function quote(): Promise<Quote | null> {
  if (cache && Date.now() - cache.at < 60_000) return cache.quote;
  for (const [source, read] of SOURCES) {
    try {
      const cadPerSol = await read();
      if (Number.isFinite(cadPerSol) && cadPerSol > 0) {
        cache = { at: Date.now(), quote: { cadPerSol, source } };
        return cache.quote;
      }
    } catch { /* try the next source */ }
  }
  return cache?.quote ?? null; // all down: a stale price is better than none
}

export async function GET() {
  const q = await quote();
  if (!q) return Response.json({ error: "The SOL price is unavailable right now." }, { status: 502 });
  return Response.json(
    { cadPerSol: q.cadPerSol, solPerCad: 1 / q.cadPerSol, source: q.source, fetchedAt: new Date(cache?.at ?? Date.now()).toISOString() },
    { headers: { "Cache-Control": "public, s-maxage=60, stale-while-revalidate=300" } },
  );
}
