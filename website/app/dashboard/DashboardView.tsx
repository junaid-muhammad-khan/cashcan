"use client";

import { AppFooter, AppHeader } from "@/components/AppChrome";
import { useEffect, useRef, useState } from "react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";
import { CATEGORIES, DETECTIONS, HISTOGRAMS, OUTCOMES, RANGE_ORDER, RANGES, REWARD_PER_CONTAINER_SOL, type Category, type Detection, type RangeKey } from "./data";

gsap.registerPlugin(useGSAP);

// Live SOL -> CAD rate from CoinGecko's public API (CORS-enabled), refreshed every minute.
function useSolCad() {
  const [rate, setRate] = useState<number | null>(null);
  const [updated, setUpdated] = useState<Date | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let alive = true;
    async function load() {
      try {
        const r = await fetch("https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=cad", { cache: "no-store" });
        if (!r.ok) throw new Error(String(r.status));
        const cad = (await r.json())?.solana?.cad;
        if (typeof cad !== "number") throw new Error("no rate");
        if (alive) { setRate(cad); setUpdated(new Date()); setFailed(false); }
      } catch {
        if (alive) setFailed(true); // keep showing the last good rate, if any
      }
    }
    load();
    const id = setInterval(load, 60_000);
    return () => { alive = false; clearInterval(id); };
  }, []);
  return { rate, updated, failed };
}

const cad = new Intl.NumberFormat("en-CA", { style: "currency", currency: "CAD" });
const timeFmt = new Intl.DateTimeFormat("en-CA", { hour: "numeric", minute: "2-digit" });

const S = { stroke: "currentColor", fill: "none", strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true };

function ItemIcon({ icon }: { icon: Detection["icon"] }) {
  const p = { ...S, width: 16, height: 16, viewBox: "0 0 24 24", strokeWidth: 1.7 };
  if (icon === "cup") return <svg {...p}><path d="M5 7h14l-1.6 13H6.6z" /><path d="M4 7h16M9 4h6" /><path d="M9 12c1 1.5 5 1.5 6 0" /></svg>;
  if (icon === "box") return <svg {...p}><path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z" /><path d="M4 7.5l8 4.5 8-4.5M12 12v9" /></svg>;
  if (icon === "can") return <svg {...p}><ellipse cx="12" cy="5" rx="6" ry="2" /><path d="M6 5v14c0 1.1 2.7 2 6 2s6-.9 6-2V5" /></svg>;
  return <svg {...p}><path d="M5 19c5 1 12-3 14-12" /><path d="M5 19c-1-5 2-10 7-12" /><path d="M5 19c3-2 6-2 8 1" /><path d="M17 4l2 3" /></svg>;
}

const Arrow = () => <svg {...S} width={11} height={11} viewBox="0 0 24 24" strokeWidth={2.4}><path d="M7 17L17 7M8 7h9v9" /></svg>;

function shortWallet(w: string) {
  return `${w.slice(0, 4)}…${w.slice(-4)}`;
}

const SOLANA_RE = /^[1-9A-HJ-NP-Za-km-z]{32,44}$/;

export default function DashboardView({ firstName, walletAddress, onSaveWallet, welcome }: { firstName: string; walletAddress: string | null; onSaveWallet?: (wallet: string) => Promise<void>; welcome: boolean }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [walletErr, setWalletErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  async function saveWallet() {
    const w = draft.trim();
    if (!SOLANA_RE.test(w)) { setWalletErr("Solana addresses are 32–44 letters and numbers. Paste it again."); return; }
    setSaving(true); setWalletErr(null);
    try { await onSaveWallet?.(w); setEditing(false); } catch (e) { setWalletErr((e as Error).message); }
    setSaving(false);
  }
  const root = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const [range, setRange] = useState<RangeKey>("week");
  const [menuOpen, setMenuOpen] = useState(false);
  const [open, setOpen] = useState<number | null>(null);
  const [hidden, setHidden] = useState<Set<Category>>(new Set());
  const { rate, updated, failed } = useSolCad();

  const R = RANGES[range];
  const pct = Math.round((100 * R.confirmed) / R.total);
  const H = HISTOGRAMS[range];
  const totals: Record<Category, number> = { cans: 0, organics: 0, waste: 0 };
  for (const b of H.buckets) for (const c of CATEGORIES) totals[c.key] += b[c.key];
  const shown = CATEGORIES.filter((c) => !hidden.has(c.key));
  const bucketTotal = (b: (typeof H.buckets)[number]) => shown.reduce((s, c) => s + b[c.key], 0);
  // Six even axis steps, using the smallest "nice" step that leaves ~10% headroom above the tallest bar.
  const rough = (Math.max(1, ...H.buckets.map(bucketTotal)) * 1.1) / 6;
  const step = [1, 2, 4, 5, 8, 10, 15, 20, 25, 50, 100, 200, 250, 500].find((s) => s >= rough) ?? 1000;
  const max = step * 6;
  const ticks = Array.from({ length: 7 }, (_, i) => Math.round((i * max) / 6));
  const labelEvery = H.buckets.length > 14 ? 5 : H.buckets.length > 8 ? 2 : 1;
  const toggle = (k: Category) => setHidden((h) => {
    const n = new Set(h);
    if (n.has(k)) n.delete(k); else if (n.size < CATEGORIES.length - 1) n.add(k); // keep at least one visible
    return n;
  });

  const containers = totals.cans;
  const sol = containers * REWARD_PER_CONTAINER_SOL;
  const detections = DETECTIONS;

  // Close the range menu on outside click / Escape.
  useEffect(() => {
    if (!menuOpen) return;
    const onDown = (e: MouseEvent) => { if (!menuRef.current?.contains(e.target as Node)) setMenuOpen(false); };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setMenuOpen(false); };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onDown); document.removeEventListener("keydown", onKey); };
  }, [menuOpen]);

  // Entrance: cards rise in once.
  useGSAP(() => {
    const mm = gsap.matchMedia();
    mm.add("(prefers-reduced-motion: no-preference)", () => {
      gsap.from(".db-rise", { y: 16, autoAlpha: 0, duration: 0.6, ease: "power3.out", stagger: 0.06 });
    });
    return () => mm.revert();
  }, { scope: root });

  // Bars grow and the SOL total counts up whenever the range changes.
  useGSAP(() => {
    const mm = gsap.matchMedia();
    mm.add("(prefers-reduced-motion: no-preference)", () => {
      gsap.from(".db-hcol", { scaleY: 0, duration: 0.7, ease: "power3.out", stagger: 0.025, transformOrigin: "50% 100%" });
      const el = root.current?.querySelector<HTMLElement>(".db-sol-num");
      if (el) {
        const o = { v: 0 };
        gsap.to(o, { v: sol, duration: 1.1, ease: "power2.out", onUpdate: () => { el.textContent = o.v.toFixed(3); } });
      }
    });
    return () => mm.revert();
  }, { scope: root, dependencies: [range] });

  return (
    <div className="db" ref={root}>
      <AppHeader current="dashboard" />

      <main className="db-wrap">
        <div className="db-inner">
          {welcome && (
            <div className="db-welcome" role="status">
              Your account is ready. This is your dashboard: every item you drop at a CashCan bin will show up here.
            </div>
          )}

          <div className="db-greet">
            <div>
              <h1>A better sort starts here, {firstName}.</h1>
              <p>Your week in sorting. A few small actions, a little less confusion.</p>
            </div>
            <div className="db-range" ref={menuRef}>
              <button type="button" className="db-pill db-range-btn" aria-haspopup="menu" aria-expanded={menuOpen} onClick={() => setMenuOpen((o) => !o)}>
                <svg {...S} width={15} height={15} viewBox="0 0 24 24" strokeWidth={2}><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M3 10h18M8 3v4M16 3v4" /></svg>
                {R.label}
                <svg {...S} width={14} height={14} viewBox="0 0 24 24" strokeWidth={2}><path d="M6 9l6 6 6-6" /></svg>
              </button>
              {menuOpen && (
                <div className="db-menu" role="menu">
                  {RANGE_ORDER.map((k) => (
                    <button key={k} type="button" role="menuitemradio" aria-checked={range === k} className="db-menu-item"
                      onClick={() => { setRange(k); setOpen(null); setMenuOpen(false); }}>
                      {RANGES[k].label}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className="db-layout">
            {/* ===== left ===== */}
            <div className="db-col">
              <section className="db-card db-rise db-recent" aria-labelledby="rd-h">
                <div className="db-recent-head">
                  <h2 id="rd-h">Recent detections</h2>
                  <div className="db-meta">Today, 7 November · Kitchen station</div>
                  <div className="db-recent-actions">
                    <a href="#activity" className="db-link">View all activity <Arrow /></a>
                  </div>
                </div>
                <ul className="db-det-list">
                  {detections.map((d) => {
                    const isOpen = open === d.id;
                    const status = OUTCOMES.find((o) => o.key === d.kind)!;
                    return (
                      <li key={d.id}>
                        <button type="button" className={`db-det${isOpen ? " open" : ""}`} aria-expanded={isOpen} onClick={() => setOpen(isOpen ? null : d.id)}>
                          <span className="db-det-row">
                            <span className="db-det-icon"><ItemIcon icon={d.icon} /></span>
                            <span><b>{d.item}</b><small>{d.note}</small></span>
                          </span>
                          <span className="db-route">{d.route}</span>
                          <span className={`db-status db-status-${d.kind}`}><i />{status.status}</span>
                          {isOpen && <span className="db-detail">{d.detail}</span>}
                          <span className="db-time">{d.time}</span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
                {detections.length === 0 && <p className="db-empty">No recent detections in this group.</p>}
                <div className="db-recent-foot">
                  <p>Sample routes illustrate the flow, not official acceptance rules. Confirm with your local collection program.</p>
                  <p className="strong">Only cans &amp; containers earn SOL for now. Reward rates are placeholders.</p>
                </div>
              </section>
            </div>

            {/* ===== right ===== */}
            <div className="db-col db-right">
              <section id="redeem" className="db-rewards db-rise" aria-labelledby="rw-h">
                <div className="db-rewards-main">
                  <div className="db-rewards-head">
                    <h2 id="rw-h">Your rewards</h2>
                    <span className="db-badge">{R.label} · Demo data</span>
                  </div>
                  <div className="db-sol" aria-label={`${sol.toFixed(3)} SOL earned`}>
                    <span className="db-sol-num">{sol.toFixed(3)}</span>
                    <span className="db-sol-unit">SOL</span>
                  </div>
                  <div className="db-cad">
                    {rate !== null ? <>≈ <b>{cad.format(sol * rate)}</b> CAD</> : failed ? "CAD value unavailable right now" : "Loading CAD value…"}
                  </div>
                  <div className="db-rate">
                    <span className={`db-live${rate !== null && !failed ? "" : " off"}`} aria-hidden="true" />
                    {rate !== null
                      ? <>Live rate · 1 SOL = {cad.format(rate)}{updated && <> · updated {timeFmt.format(updated)}</>}{failed && " · couldn't refresh"}</>
                      : failed ? "Live rate unavailable" : "Fetching live rate…"}
                    <span className="db-rate-src">via CoinGecko</span>
                  </div>
                  <p className="db-body">
                    From <b>{containers}</b> reward-eligible containers · {REWARD_PER_CONTAINER_SOL} SOL each. Paid on Solana devnet, which has no cash value yet.
                  </p>
                </div>
                <div className="db-rewards-side">
                <div className="db-wallet">
                  <span>
                    <svg {...S} width={15} height={15} viewBox="0 0 24 24" strokeWidth={1.8}><rect x="3" y="6" width="18" height="14" rx="2" /><path d="M3 10h18M16 15h2" /></svg>
                    Wallet
                  </span>
                  <span className="val" title={walletAddress ?? undefined}>{walletAddress ? `${shortWallet(walletAddress)} · devnet` : "Not connected"}</span>
                </div>
                {editing ? (
                  <div style={{ marginTop: 12 }}>
                    <label htmlFor="db-wallet-input" className="sr-only">Solana wallet address</label>
                    <input id="db-wallet-input" type="text" value={draft} onChange={(e) => setDraft(e.target.value)} spellCheck={false} autoComplete="off"
                      placeholder="Paste your Solana wallet address" style={{ width: "100%", padding: "9px 10px", borderRadius: 8, border: "1px solid #36574a", background: "#17352a", color: "#fff", fontFamily: "monospace", fontSize: 12 }} />
                    {walletErr && <p role="alert" className="db-small" style={{ color: "#ffb4a8" }}>{walletErr}</p>}
                    <div style={{ display: "flex", gap: 10, marginTop: 10 }}>
                      <button type="button" className="db-lime" disabled={saving} onClick={saveWallet}>{saving ? "Saving…" : "Save wallet"}</button>
                      <button type="button" className="db-lime" onClick={() => { setEditing(false); setWalletErr(null); }}>Cancel</button>
                    </div>
                  </div>
                ) : (
                  <button type="button" className="db-lime" onClick={() => { setDraft(walletAddress ?? ""); setEditing(true); }}>
                    {walletAddress ? "Change wallet" : "Add wallet"}
                    <svg {...S} width={14} height={14} viewBox="0 0 24 24" strokeWidth={2.2}><path d="M5 12h14M13 6l6 6-6 6" /></svg>
                  </button>
                )}
                <p className="db-small">Rewards go to this wallet. A wallet isn&apos;t needed for activity history.</p>
                </div>
              </section>

              <section className="db-card db-learn db-rise" aria-labelledby="learn-h">
                <div className="db-learn-head">
                  <div>
                    <h2 id="learn-h">Every sort is a chance to learn</h2>
                    <p>{R.total} detected items · {R.long}</p>
                  </div>
                  <a href="#insights" className="db-link">Explore insights <Arrow /></a>
                </div>

                <div className="db-learn-grid">
                  <div className="db-legend" role="group" aria-label="Bins: click to show or hide">
                    {CATEGORIES.map((c) => {
                      const on = !hidden.has(c.key);
                      return (
                        <button key={c.key} type="button" className={`db-leg${on ? "" : " off"}`} aria-pressed={on} onClick={() => toggle(c.key)}>
                          <span className="db-leg-sw" style={{ background: c.color }} />
                          <span className="db-leg-txt">
                            <small>{c.label}</small>
                            <strong>{totals[c.key]}</strong>
                            <em>{Math.round((100 * totals[c.key]) / R.total)}% of items</em>
                          </span>
                        </button>
                      );
                    })}
                    <small className="db-leg-note">{pct}% of items had a confirmed sorting outcome. Click a bin to show or hide it.</small>
                  </div>

                  <div>
                    <div className="db-chart-title">Items sorted {H.unit}, by bin</div>
                    <div className="db-axis-label">Items</div>
                    <div className="db-chart">
                      {ticks.map((t, i) => (
                        <div key={t} className={`db-tick${i === 0 ? " base" : ""}`} style={{ bottom: `${(i / 6) * 100}%` }} aria-hidden="true">
                          <span>{t}</span><i />
                        </div>
                      ))}
                      <div className="db-hist" role="img"
                        aria-label={`Histogram of items sorted ${H.unit}: ${shown.map((c) => `${totals[c.key]} ${c.label.toLowerCase()}`).join(", ")}`}
                        style={{ gridTemplateColumns: `repeat(${H.buckets.length}, minmax(0, 1fr))` }}>
                        {H.buckets.map((b) => {
                          const n = bucketTotal(b);
                          return (
                            <div key={b.label} className="db-hcol" style={{ height: `${(n / max) * 100}%` }}
                              title={`${b.label}: ${n} items (${shown.map((c) => `${b[c.key]} ${c.label.toLowerCase()}`).join(", ")})`}>
                              {shown.map((c) => (
                                <i key={c.key} style={{ flexGrow: b[c.key], background: c.color }} />
                              ))}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                    <div className="db-hist-labels" style={{ gridTemplateColumns: `repeat(${H.buckets.length}, minmax(0, 1fr))` }}>
                      {H.buckets.map((b, i) => <span key={b.label}>{i % labelEvery === 0 ? b.label : ""}</span>)}
                    </div>
                    <p className="db-foot">{R.total} items total · {R.long} · Demo data</p>
                  </div>
                </div>
              </section>
            </div>
          </div>

          <AppFooter note="Demo data · Metro Vancouver · All times local" />
        </div>
      </main>
    </div>
  );
}
