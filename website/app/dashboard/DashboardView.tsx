"use client";

import { AppFooter, AppHeader } from "@/components/AppChrome";
import { useCallback, useEffect, useRef, useState } from "react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";
import { explorerAddress, explorerTx, type Activity, type Drop, type RangeKey } from "@/lib/activity";
import type { HeldRelease } from "@/lib/faceApi";
import type { Rate } from "@/lib/rate";
import { CATEGORIES, RANGE_LABELS, RANGE_ORDER } from "./data";

gsap.registerPlugin(useGSAP);

// Live SOL -> CAD rate from our own /api/rate (the same rate source the payouts use), refreshed every minute.
function useSolCad() {
  const [rate, setRate] = useState<Rate | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let alive = true;
    async function load() {
      try {
        const r = await fetch("/api/rate", { cache: "no-store" });
        const body = await r.json();
        if (!r.ok || typeof body?.cadPerSol !== "number") throw new Error("no rate");
        if (alive) { setRate(body as Rate); setFailed(false); }
      } catch {
        if (alive) setFailed(true); // keep showing the last good rate, if any
      }
    }
    load();
    const id = setInterval(load, 60_000);
    return () => { alive = false; clearInterval(id); };
  }, []);
  return { rate, failed };
}

// Devnet balance of the user's wallet (website /api/balance).
function useBalance(address: string | null, refresh: number) {
  const [sol, setSol] = useState<number | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!address) { setSol(null); return; }
    let alive = true;
    fetch(`/api/balance?address=${encodeURIComponent(address)}`, { cache: "no-store" })
      .then(async (r) => { const b = await r.json(); if (!r.ok) throw new Error(); if (alive) { setSol(b.sol); setFailed(false); } })
      .catch(() => { if (alive) setFailed(true); });
    return () => { alive = false; };
  }, [address, refresh]);
  return { sol, failed };
}

type Load = { status: "loading" } | { status: "error"; message: string } | { status: "ready"; data: Activity };

const cad = new Intl.NumberFormat("en-CA", { style: "currency", currency: "CAD" });
const timeFmt = new Intl.DateTimeFormat("en-CA", { hour: "numeric", minute: "2-digit" });
const dayFmt = new Intl.DateTimeFormat("en-CA", { month: "short", day: "numeric" });
const fmtSol = (s: number) => (s === 0 ? "0" : s < 0.000001 ? "< 0.000001" : s.toLocaleString("en-CA", { maximumFractionDigits: 6 }));

const S = { stroke: "currentColor", fill: "none", strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true };

function ItemIcon({ cls }: { cls: string }) {
  const p = { ...S, width: 16, height: 16, viewBox: "0 0 24 24", strokeWidth: 1.7 };
  if (cls === "cans") return <svg {...p}><ellipse cx="12" cy="5" rx="6" ry="2" /><path d="M6 5v14c0 1.1 2.7 2 6 2s6-.9 6-2V5" /></svg>;
  if (cls === "organics") return <svg {...p}><path d="M5 19c5 1 12-3 14-12" /><path d="M5 19c-1-5 2-10 7-12" /><path d="M5 19c3-2 6-2 8 1" /><path d="M17 4l2 3" /></svg>;
  return <svg {...p}><path d="M5 7h14l-1.6 13H6.6z" /><path d="M4 7h16M9 4h6" /></svg>;
}

const Arrow = () => <svg {...S} width={11} height={11} viewBox="0 0 24 24" strokeWidth={2.4}><path d="M7 17L17 7M8 7h9v9" /></svg>;

const ITEM_NAME: Record<string, string> = { cans: "Can or container", organics: "Organics", waste: "Waste" };
const REASON: Record<string, string> = {
  not_recognised: "Nobody was recognised at the bin, so there was no reward.",
  low_confidence: "The bin wasn't sure what the item was, so it earned nothing.",
  not_reward_eligible: "Only cans and deposit containers earn a reward for now.",
  cooldown: "Dropped too soon after your last paid item, so it earned nothing.",
};

/** Label and pill style for a drop's payout state. */
function statusOf(d: Drop): { label: string; kind: "confirmed" | "review" | "flagged" | "muted" } {
  switch (d.payout_status) {
    case "paid": return { label: "Paid", kind: "confirmed" };
    case "held": return { label: "Held · add a wallet", kind: "review" };
    case "pending": case "sending": return { label: "Paying", kind: "review" };
    case "failed": return { label: "Retrying", kind: "flagged" };
    default: return { label: "No reward", kind: "muted" };
  }
}

function shortWallet(w: string) {
  return `${w.slice(0, 4)}…${w.slice(-4)}`;
}

const SOLANA_RE = /^[1-9A-HJ-NP-Za-km-z]{32,44}$/;

export default function DashboardView({ firstName, walletAddress, onSaveWallet, welcome, load, demo = false }: {
  firstName: string;
  walletAddress: string | null;
  onSaveWallet?: (wallet: string) => Promise<HeldRelease | void>;
  welcome: boolean;
  load: (range: RangeKey) => Promise<Activity>;
  demo?: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [walletErr, setWalletErr] = useState<string | null>(null);
  const [walletMsg, setWalletMsg] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [range, setRange] = useState<RangeKey>("week");
  const [state, setState] = useState<Load>({ status: "loading" });
  const [nonce, setNonce] = useState(0);
  const root = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const { rate, failed: rateFailed } = useSolCad();
  const balance = useBalance(walletAddress, nonce);

  useEffect(() => {
    let alive = true;
    setState((s) => (s.status === "ready" ? s : { status: "loading" }));
    load(range)
      .then((data) => { if (alive) setState({ status: "ready", data }); })
      .catch((e) => { if (alive) setState({ status: "error", message: (e as Error).message || "Your activity couldn't be loaded." }); });
    return () => { alive = false; };
  }, [load, range, nonce]);
  const reload = useCallback(() => setNonce((n) => n + 1), []);

  async function saveWallet() {
    const w = draft.trim();
    if (!SOLANA_RE.test(w)) { setWalletErr("Solana addresses are 32–44 letters and numbers. Paste it again."); return; }
    setSaving(true); setWalletErr(null); setWalletMsg(null);
    try {
      const r = await onSaveWallet?.(w);
      setEditing(false);
      if (r?.held_error) setWalletMsg(r.held_error);
      else if (r?.held_queued) setWalletMsg(`${r.held_paid ?? 0} of ${r.held_queued} held reward${r.held_queued === 1 ? "" : "s"} paid to this wallet${(r.held_paid ?? 0) < r.held_queued ? "; the rest follow within a few minutes" : ""}.`);
      reload();
    } catch (e) { setWalletErr((e as Error).message); }
    setSaving(false);
  }

  // Close the range menu on outside click / Escape.
  useEffect(() => {
    if (!menuOpen) return;
    const onDown = (e: MouseEvent) => { if (!menuRef.current?.contains(e.target as Node)) setMenuOpen(false); };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setMenuOpen(false); };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onDown); document.removeEventListener("keydown", onKey); };
  }, [menuOpen]);

  const data = state.status === "ready" ? state.data : null;
  const T = data?.totals;

  useGSAP(() => {
    const mm = gsap.matchMedia();
    mm.add("(prefers-reduced-motion: no-preference)", () => {
      gsap.from(".db-rise", { y: 16, autoAlpha: 0, duration: 0.6, ease: "power3.out", stagger: 0.06 });
    });
    return () => mm.revert();
  }, { scope: root });

  useGSAP(() => {
    if (!data) return;
    const mm = gsap.matchMedia();
    mm.add("(prefers-reduced-motion: no-preference)", () => {
      gsap.from(".db-hcol", { scaleY: 0, duration: 0.7, ease: "power3.out", stagger: 0.02, transformOrigin: "50% 100%" });
    });
    return () => mm.revert();
  }, { scope: root, dependencies: [data] });

  // ---- histogram (real series) ----
  const series = data?.series ?? [];
  const shown = CATEGORIES.filter((c) => !hidden.has(c.key));
  const bucketTotal = (b: (typeof series)[number]) => shown.reduce((s, c) => s + b[c.key], 0);
  const rough = (Math.max(1, ...series.map(bucketTotal)) * 1.1) / 6;
  const step = [1, 2, 4, 5, 8, 10, 15, 20, 25, 50, 100, 200, 250, 500].find((s) => s >= rough) ?? 1000;
  const max = step * 6;
  const ticks = Array.from({ length: 7 }, (_, i) => Math.round((i * max) / 6));
  const labelEvery = series.length > 14 ? 5 : series.length > 8 ? 3 : 1;
  const toggle = (k: string) => setHidden((h) => {
    const n = new Set(h);
    if (n.has(k)) n.delete(k); else if (n.size < CATEGORIES.length - 1) n.add(k);
    return n;
  });

  const owedCents = (T?.held_cents ?? 0) + (T?.pending_cents ?? 0);
  const recent = data?.recent ?? [];

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
          {demo && <div className="db-welcome" role="note">Preview with demo data (local development only).</div>}

          <div className="db-greet">
            <div>
              <h1>A better sort starts here, {firstName}.</h1>
              <p>Every item you drop at a CashCan bin, and what it earned.</p>
            </div>
            <div className="db-range" ref={menuRef}>
              <button type="button" className="db-pill db-range-btn" aria-haspopup="menu" aria-expanded={menuOpen} onClick={() => setMenuOpen((o) => !o)}>
                <svg {...S} width={15} height={15} viewBox="0 0 24 24" strokeWidth={2}><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M3 10h18M8 3v4M16 3v4" /></svg>
                {RANGE_LABELS[range]}
                <svg {...S} width={14} height={14} viewBox="0 0 24 24" strokeWidth={2}><path d="M6 9l6 6 6-6" /></svg>
              </button>
              {menuOpen && (
                <div className="db-menu" role="menu">
                  {RANGE_ORDER.map((k) => (
                    <button key={k} type="button" role="menuitemradio" aria-checked={range === k} className="db-menu-item"
                      onClick={() => { setRange(k); setOpen(null); setMenuOpen(false); }}>
                      {RANGE_LABELS[k]}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          {state.status === "error" && (
            <div className="db-welcome db-error" role="alert">
              {state.message} <button type="button" className="db-link" onClick={reload}>Try again</button>
            </div>
          )}

          <div className="db-layout">
            {/* ===== left: recent drops ===== */}
            <div className="db-col">
              <section className="db-card db-rise db-recent" aria-labelledby="rd-h" aria-busy={state.status === "loading"}>
                <div className="db-recent-head">
                  <h2 id="rd-h">Recent drops</h2>
                  <div className="db-meta">{RANGE_LABELS[range]}{data ? ` · ${T!.items} item${T!.items === 1 ? "" : "s"}` : ""}</div>
                </div>
                {state.status === "loading" && (
                  <ul className="db-det-list" aria-hidden="true">
                    {[0, 1, 2].map((i) => <li key={i}><div className="db-det db-skel"><span className="db-skel-bar" /></div></li>)}
                  </ul>
                )}
                {data && recent.length > 0 && (
                  <ul className="db-det-list">
                    {recent.map((d) => {
                      const isOpen = open === d.interaction_id;
                      const st = statusOf(d);
                      const when = new Date(d.created_at);
                      const reward = d.payout_status === "paid" && d.sol != null ? `${fmtSol(d.sol)} SOL` : d.reward_cents ? `${d.reward_cents}¢` : "";
                      return (
                        <li key={d.interaction_id}>
                          <button type="button" className={`db-det${isOpen ? " open" : ""}`} aria-expanded={isOpen} onClick={() => setOpen(isOpen ? null : d.interaction_id)}>
                            <span className="db-det-row">
                              <span className="db-det-icon"><ItemIcon cls={d.item_class} /></span>
                              <span><b>{ITEM_NAME[d.item_class] ?? d.item_class}</b><small>{d.bin_name ?? d.bin_id ?? "CashCan bin"}</small></span>
                            </span>
                            <span className="db-route">{reward || "—"}</span>
                            <span className={`db-status db-status-${st.kind}`}><i />{st.label}</span>
                            {isOpen && (
                              <span className="db-detail">
                                {d.payout_status === "paid" && <>Paid {d.reward_cents}¢{d.cad_per_sol ? ` at 1 SOL = ${cad.format(d.cad_per_sol)}` : ""}. </>}
                                {d.payout_status === "held" && <>Earned {d.reward_cents}¢. It is held until you add a wallet, then paid automatically. </>}
                                {(d.payout_status === "pending" || d.payout_status === "sending") && <>Earned {d.reward_cents}¢. The payout is on its way. </>}
                                {d.payout_status === "failed" && <>Earned {d.reward_cents}¢. The payout didn&apos;t go through yet and is retried automatically. </>}
                                {d.payout_status === "none" && (REASON[d.reason ?? ""] ?? "This item earned no reward.")}
                              </span>
                            )}
                            <span className="db-time">{dayFmt.format(when)} · {timeFmt.format(when)}</span>
                          </button>
                          {isOpen && d.tx_signature && (d.tx_signature.startsWith("demo_")
                            ? <p className="db-meta db-tx">Demo payout: recorded as paid, but no SOL was sent.</p>
                            : <a className="db-link db-tx" href={explorerTx(d.tx_signature)} target="_blank" rel="noreferrer">View transaction on Solana Explorer (devnet) <Arrow /></a>)}
                        </li>
                      );
                    })}
                  </ul>
                )}
                {data && recent.length === 0 && (
                  <p className="db-empty">
                    No drops {range === "today" ? "today" : `in the ${RANGE_LABELS[range].toLowerCase()}`} yet. Stand in front of a CashCan bin, let it recognise
                    you, and drop a can in the Cans opening: it shows up here with its reward.
                  </p>
                )}
                <div className="db-recent-foot">
                  <p className="strong">Cans and deposit containers earn 5¢ each (half the BC deposit), paid in Solana devnet SOL at the live rate.</p>
                </div>
              </section>
            </div>

            {/* ===== right ===== */}
            <div className="db-col db-right">
              <section id="redeem" className="db-rewards db-rise" aria-labelledby="rw-h">
                <div className="db-rewards-main">
                  <div className="db-rewards-head">
                    <h2 id="rw-h">Your rewards</h2>
                    <span className="db-badge">{RANGE_LABELS[range]}{demo ? " · Demo data" : ""}</span>
                  </div>
                  <div className="db-sol" aria-label={`${T ? fmtSol(T.paid_sol) : "0"} SOL paid`}>
                    <span className="db-sol-num">{T ? fmtSol(T.paid_sol) : "–"}</span>
                    <span className="db-sol-unit">SOL</span>
                  </div>
                  <div className="db-cad">
                    {T ? <><b>{cad.format(T.paid_cad)}</b> CAD when paid{rate && T.paid_sol > 0 ? <> · worth {cad.format(T.paid_sol * rate.cadPerSol)} today</> : null}</> : "Loading…"}
                  </div>
                  <div className="db-rate">
                    <span className={`db-live${rate && !rateFailed ? "" : " off"}`} aria-hidden="true" />
                    {rate ? <>Live rate · 1 SOL = {cad.format(rate.cadPerSol)} · {rate.source}{rateFailed && " · couldn't refresh"}</> : rateFailed ? "Live rate unavailable" : "Fetching live rate…"}
                  </div>
                  {T && (
                    <p className="db-body">
                      <b>{T.paid_count}</b> paid item{T.paid_count === 1 ? "" : "s"}
                      {T.held_count > 0 && <> · <b>{T.held_count}</b> held ({T.held_cents}¢) until you add a wallet</>}
                      {T.pending_count + T.failed_count > 0 && <> · <b>{T.pending_count + T.failed_count}</b> on the way</>}
                      {owedCents === 0 && T.paid_count === 0 && <> yet</>}. Paid on Solana devnet, which has no cash value.
                    </p>
                  )}
                </div>
                <div className="db-rewards-side">
                  <div className="db-wallet">
                    <span>
                      <svg {...S} width={15} height={15} viewBox="0 0 24 24" strokeWidth={1.8}><rect x="3" y="6" width="18" height="14" rx="2" /><path d="M3 10h18M16 15h2" /></svg>
                      Wallet
                    </span>
                    <span className="val" title={walletAddress ?? undefined}>
                      {walletAddress ? <a href={explorerAddress(walletAddress)} target="_blank" rel="noreferrer">{shortWallet(walletAddress)} · devnet</a> : "Not connected"}
                    </span>
                  </div>
                  {walletAddress && (
                    <p className="db-small">Balance: {balance.sol != null ? `${fmtSol(balance.sol)} SOL` : balance.failed ? "unavailable right now" : "…"}</p>
                  )}
                  {!walletAddress && (T?.held_count ?? 0) > 0 && (
                    <p className="db-small" role="status">You have {T!.held_cents}¢ in held rewards. Add a wallet and they are paid right away.</p>
                  )}
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
                  {walletMsg && <p className="db-small" role="status">{walletMsg}</p>}
                  <p className="db-small">Rewards go to this wallet. A wallet isn&apos;t needed for activity history.</p>
                </div>
              </section>

              <section className="db-card db-learn db-rise" aria-labelledby="learn-h">
                <div className="db-learn-head">
                  <div>
                    <h2 id="learn-h">What you sorted</h2>
                    <p>{data ? `${T!.items} item${T!.items === 1 ? "" : "s"} · ${RANGE_LABELS[range].toLowerCase()}` : "Loading…"}</p>
                  </div>
                </div>

                <div className="db-learn-grid">
                  <div className="db-legend" role="group" aria-label="Bins: click to show or hide">
                    {CATEGORIES.map((c) => {
                      const on = !hidden.has(c.key);
                      const n = data?.by_bin[c.key] ?? 0;
                      return (
                        <button key={c.key} type="button" className={`db-leg${on ? "" : " off"}`} aria-pressed={on} onClick={() => toggle(c.key)}>
                          <span className="db-leg-sw" style={{ background: c.color }} />
                          <span className="db-leg-txt">
                            <small>{c.label}</small>
                            <strong>{data ? n : "–"}</strong>
                            <em>{T && T.items > 0 ? `${Math.round((100 * n) / T.items)}% of items` : "no items yet"}</em>
                          </span>
                        </button>
                      );
                    })}
                    <small className="db-leg-note">Click a bin to show or hide it.</small>
                  </div>

                  <div>
                    <div className="db-chart-title">Items sorted {data?.unit ?? ""}, by bin</div>
                    <div className="db-axis-label">Items</div>
                    <div className="db-chart">
                      {ticks.map((t, i) => (
                        <div key={t} className={`db-tick${i === 0 ? " base" : ""}`} style={{ bottom: `${(i / 6) * 100}%` }} aria-hidden="true">
                          <span>{t}</span><i />
                        </div>
                      ))}
                      <div className="db-hist" role="img"
                        aria-label={`Items sorted ${data?.unit ?? ""}: ${shown.map((c) => `${data?.by_bin[c.key] ?? 0} ${c.label.toLowerCase()}`).join(", ")}`}
                        style={{ gridTemplateColumns: `repeat(${Math.max(1, series.length)}, minmax(0, 1fr))` }}>
                        {series.map((b) => {
                          const n = bucketTotal(b);
                          return (
                            <div key={b.label + b.start} className="db-hcol" style={{ height: `${(n / max) * 100}%` }}
                              title={`${b.label}: ${n} items (${shown.map((c) => `${b[c.key]} ${c.label.toLowerCase()}`).join(", ")})`}>
                              {shown.map((c) => (
                                <i key={c.key} style={{ flexGrow: b[c.key], background: c.color }} />
                              ))}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                    <div className="db-hist-labels" style={{ gridTemplateColumns: `repeat(${Math.max(1, series.length)}, minmax(0, 1fr))` }}>
                      {series.map((b, i) => <span key={b.label + b.start}>{i % labelEvery === 0 ? b.label : ""}</span>)}
                    </div>
                    <p className="db-foot">{data ? `${T!.items} items · ${RANGE_LABELS[range].toLowerCase()} · times in ${data.timezone}` : ""}{demo ? " · Demo data" : ""}</p>
                  </div>
                </div>
              </section>
            </div>
          </div>

          <AppFooter note={demo ? "Demo data · local preview" : "Your drops at CashCan bins · Solana devnet"} />
        </div>
      </main>
    </div>
  );
}
