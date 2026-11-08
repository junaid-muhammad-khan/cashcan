"use client";

import { useCallback, useEffect, useState } from "react";
import { CONTAINERS, cashBackCents } from "@/lib/prices";
import { Rate, cadToSol, centsToCad, fmtCad, fmtSol, parseAmount, solToCad } from "@/lib/rate";

const MAX = 999;

export default function RewardCalculator() {
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [rate, setRate] = useState<Rate | null>(null);
  const [rateErr, setRateErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [cadText, setCadText] = useState("1");
  const [solText, setSolText] = useState("");

  const loadRate = useCallback(async () => {
    setLoading(true);
    setRateErr(null);
    try {
      const res = await fetch("/api/rate", { cache: "no-store" });
      const body = await res.json();
      if (!res.ok) throw new Error(body?.error ?? "unavailable");
      setRate(body as Rate);
    } catch {
      setRateErr("We couldn't read the live SOL price. The cash totals still work; try again in a moment.");
    }
    setLoading(false);
  }, []);
  useEffect(() => { loadRate(); }, [loadRate]);

  // Converter: type in either box, the other follows. Starts from C$1 once the rate arrives.
  useEffect(() => {
    if (rate && solText === "") { const c = parseAmount(cadText); setSolText(c == null ? "" : String(Number(cadToSol(c, rate).toFixed(6)))); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rate]);
  const onCad = (t: string) => { setCadText(t); const c = parseAmount(t); if (rate) setSolText(c == null ? "" : String(Number(cadToSol(c, rate).toFixed(6)))); };
  const onSol = (t: string) => { setSolText(t); const s = parseAmount(t); if (rate) setCadText(s == null ? "" : String(Number(solToCad(s, rate).toFixed(2)))); };

  const set = (id: string, n: number) => setCounts((c) => ({ ...c, [id]: Math.max(0, Math.min(MAX, Math.floor(Number.isFinite(n) ? n : 0))) }));
  const items = CONTAINERS.reduce((n, c) => n + (counts[c.id] ?? 0), 0);
  const cents = CONTAINERS.reduce((n, c) => n + (counts[c.id] ?? 0) * cashBackCents(c), 0);
  const depositCents = CONTAINERS.reduce((n, c) => n + (counts[c.id] ?? 0) * c.depositCents, 0);
  const cad = centsToCad(cents);

  return (
    <section className="calc" aria-labelledby="calc-h">
      <h2 id="calc-h" className="cat-subhead" style={{ marginTop: 0 }}>Reward calculator</h2>
      <p className="calc-lede">Pick how many of each container you bring and see what you would get back, in dollars and in SOL.</p>

      <div className="calc-grid">
        <ul className="calc-rows">
          {CONTAINERS.map((c) => {
            const n = counts[c.id] ?? 0;
            return (
              <li key={c.id}>
                <label htmlFor={`calc-${c.id}`}><b>{c.name}</b><small>{cashBackCents(c)}¢ cash back each</small></label>
                <span className="calc-step">
                  <button type="button" aria-label={`One fewer ${c.name}`} onClick={() => set(c.id, n - 1)} disabled={n === 0}>−</button>
                  <input id={`calc-${c.id}`} inputMode="numeric" value={n} onChange={(e) => set(c.id, Number(e.target.value.replace(/\D/g, "")))} />
                  <button type="button" aria-label={`One more ${c.name}`} onClick={() => set(c.id, n + 1)} disabled={n >= MAX}>+</button>
                </span>
              </li>
            );
          })}
        </ul>

        <div className="calc-total" aria-live="polite">
          <div className="calc-total-label">{items} container{items === 1 ? "" : "s"}</div>
          <div className="calc-big">{fmtCad(cad)}</div>
          <div className="calc-sub">cash back (BC deposit value {fmtCad(centsToCad(depositCents))})</div>
          <div className="calc-sol">
            {rate ? <><b>{fmtSol(cadToSol(cad, rate))} SOL</b> at today&apos;s price</> : loading ? "Reading the SOL price…" : "SOL amount unavailable"}
          </div>
          {items > 0 && <button type="button" className="calc-clear" onClick={() => setCounts({})}>Clear</button>}
        </div>
      </div>

      <div className="calc-convert">
        <h3>SOL ⇄ CAD</h3>
        <div className="calc-rate" aria-live="polite">
          {rate ? (
            <>
              <span>1 SOL = <b>{fmtCad(rate.cadPerSol)}</b></span>
              <span>C$1 = <b>{fmtSol(rate.solPerCad)} SOL</b></span>
              <small>{rate.source}, {new Date(rate.fetchedAt).toLocaleTimeString("en-CA", { hour: "numeric", minute: "2-digit" })}</small>
            </>
          ) : loading ? <span>Reading the live rate…</span> : <span className="calc-err">{rateErr}</span>}
          <button type="button" className="calc-clear" onClick={loadRate} disabled={loading}>{loading ? "Updating…" : "Refresh rate"}</button>
        </div>
        <div className="calc-pair">
          <label>Canadian dollars
            <span className="calc-field"><i>C$</i><input inputMode="decimal" value={cadText} onChange={(e) => onCad(e.target.value)} disabled={!rate} /></span>
          </label>
          <span aria-hidden="true" className="calc-eq">⇄</span>
          <label>SOL
            <span className="calc-field"><i>◎</i><input inputMode="decimal" value={solText} onChange={(e) => onSol(e.target.value)} disabled={!rate} /></span>
          </label>
        </div>
      </div>

      <p className="calc-note">CashCan pays in Solana <b>devnet</b> test tokens, which have no cash value. This calculator shows what the same amount would be worth in real SOL at today&apos;s market price, to make the rewards easy to picture. Prices move all day.</p>
    </section>
  );
}
