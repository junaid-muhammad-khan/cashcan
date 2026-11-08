// Live SOL price in CAD, read on the server. Used by /api/rate (the Prices page and dashboard) and by /api/payout
// (the rate at the moment a reward is sent). Tries Coinbase, then CoinGecko, then Kraken (all public, no key).
// Cached 60 s per server instance.
export type Quote = { cadPerSol: number; source: string; fetchedAt: number };

type Source = [string, () => Promise<number>];

const SOURCES: Source[] = [
  ["Coinbase", async () => Number((await getJson("https://api.coinbase.com/v2/prices/SOL-CAD/spot")).data.amount)],
  ["CoinGecko", async () => Number((await getJson("https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=cad")).solana.cad)],
  ["Kraken", async () => Number((Object.values((await getJson("https://api.kraken.com/0/public/Ticker?pair=SOLCAD")).result)[0] as { c: string[] }).c[0])],
];

async function getJson(url: string) {
  const res = await fetch(url, { cache: "no-store", signal: AbortSignal.timeout(4000) });
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json();
}

let cache: Quote | null = null;

/** maxAgeMs: how old a cached price may be. A payout passes a short one so it pays at (close to) the live rate. */
export async function solCadQuote(maxAgeMs = 60_000, sources: Source[] = SOURCES): Promise<Quote | null> {
  if (cache && Date.now() - cache.fetchedAt < maxAgeMs) return cache;
  for (const [source, read] of sources) {
    try {
      const cadPerSol = await read();
      if (Number.isFinite(cadPerSol) && cadPerSol > 0) {
        cache = { cadPerSol, source, fetchedAt: Date.now() };
        return cache;
      }
    } catch { /* try the next source */ }
  }
  return cache; // all down: a stale price (or null) is the caller's call
}

export function resetQuoteCache() { cache = null; }
