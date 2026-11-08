"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";
import { DETECTIONS, OUTCOMES, RANGE_ORDER, RANGES, type Detection, type Outcome, type RangeKey } from "./data";

gsap.registerPlugin(useGSAP);

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

export default function DashboardView({ firstName, walletAddress, welcome }: { firstName: string; walletAddress: string | null; welcome: boolean }) {
  const root = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const [range, setRange] = useState<RangeKey>("week");
  const [menuOpen, setMenuOpen] = useState(false);
  const [filter, setFilter] = useState<Outcome | null>(null);
  const [open, setOpen] = useState<number | null>(null);

  const R = RANGES[range];
  const pct = Math.round((100 * R.confirmed) / R.total);
  // Six even axis steps, using the smallest "nice" step that leaves ~10% headroom above the tallest bar.
  const rough = (Math.max(R.confirmed, R.flagged, R.review) * 1.1) / 6;
  const step = [1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500].find((s) => s >= rough) ?? 1000;
  const max = step * 6;
  const ticks = Array.from({ length: 7 }, (_, i) => Math.round((i * max) / 6));
  const values: Record<Outcome, number> = { confirmed: R.confirmed, flagged: R.flagged, review: R.review };
  const detections = DETECTIONS.filter((d) => !filter || d.kind === filter);

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

  // Bars grow whenever the range changes.
  useGSAP(() => {
    const mm = gsap.matchMedia();
    mm.add("(prefers-reduced-motion: no-preference)", () => {
      gsap.from(".db-bar", { scaleY: 0, duration: 0.8, ease: "power3.out", stagger: 0.08, transformOrigin: "50% 100%" });
    });
    return () => mm.revert();
  }, { scope: root, dependencies: [range] });

  const kpis = [
    { label: "Items detected", value: R.total, sub: `Across ${R.days}`, icon: null },
    { label: "Confirmed sorts", value: R.confirmed, sub: `${pct}% of detections`, icon: "check" },
    { label: "Contamination flags", value: R.flagged, sub: "Review before disposal", icon: "warn" },
    { label: "Awaiting review", value: R.review, sub: "Local rules or item unclear", icon: "clip" },
  ] as const;

  return (
    <div className="db" ref={root}>
      <header className="db-top">
        <Link href="/" className="db-logo">
          <span className="db-logo-mark">
            {/* Same bin mark as the browser-tab icon (app/icon.svg) */}
            <svg {...S} width={22} height={22} viewBox="0 0 32 32" strokeWidth={2.6} stroke="#fff">
              <path d="M7 9h18l-2 18H9z" /><path d="M5 9h22" /><path d="M12 9V6h8v3" /><path d="M13 15c1.5-1.5 4.5-1.5 6 0M16 14v8" />
            </svg>
          </span>
          <span>cashcan</span>
        </Link>
        <nav aria-label="Account" className="db-top-links">
          <Link href="/" className="db-pill">Home</Link>
          <a href="#redeem" className="db-pill">Redeem</a>
          <Link href="/account" className="db-pill">Profile</Link>
        </nav>
      </header>

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
                      onClick={() => { setRange(k); setFilter(null); setOpen(null); setMenuOpen(false); }}>
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
                    {filter && (
                      <button type="button" className="db-chip" onClick={() => setFilter(null)}>
                        {OUTCOMES.find((o) => o.key === filter)!.label} · Clear
                      </button>
                    )}
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
                  <p className="strong">Rewards not evaluated · eligibility and rates pending configuration.</p>
                </div>
              </section>

              <section id="redeem" className="db-rewards db-rise" aria-labelledby="rw-h">
                <div className="db-rewards-head">
                  <h2 id="rw-h">Your rewards</h2>
                  <svg {...S} width={18} height={18} viewBox="0 0 24 24" strokeWidth={1.8} stroke="#DDE8B0"><rect x="3" y="8" width="18" height="4" rx="1" /><path d="M5 12v9h14v-9M12 8v13" /><path d="M12 8c-1.5-3-5-3.5-5-1s5 1 5 1c1.5-3 5-3.5 5-1s-5 1-5 1" /></svg>
                </div>
                <span className="db-badge">Pending configuration</span>
                <div className="db-dash" aria-hidden="true" />
                <p className="db-muted">No crypto rewards issued</p>
                <p className="db-body">Small crypto rewards are planned for eligible detected items. Eligibility and payout rates haven&apos;t been configured yet.</p>
                <div className="db-wallet">
                  <span>
                    <svg {...S} width={15} height={15} viewBox="0 0 24 24" strokeWidth={1.8}><rect x="3" y="6" width="18" height="14" rx="2" /><path d="M3 10h18M16 15h2" /></svg>
                    Wallet
                  </span>
                  <span className="val">{walletAddress ? `${shortWallet(walletAddress)} · devnet` : "Not connected"}</span>
                </div>
                <Link href="/account" className="db-lime">
                  {walletAddress ? "Manage wallet" : "View rewards setup"}
                  <svg {...S} width={14} height={14} viewBox="0 0 24 24" strokeWidth={2.2}><path d="M5 12h14M13 6l6 6-6 6" /></svg>
                </Link>
                <p className="db-small">Keep sorting and tracking. A wallet isn&apos;t needed for activity history.</p>
              </section>
            </div>

            {/* ===== right ===== */}
            <div className="db-col db-right">
              <section className="db-kpis" aria-label="This period at a glance">
                {kpis.map((k) => (
                  <div key={k.label} className="db-card db-kpi db-rise">
                    <div className="db-kpi-head">
                      <span>{k.label}</span>
                      {k.icon === "check" && <svg {...S} width={16} height={16} viewBox="0 0 24 24" strokeWidth={1.8}><circle cx="12" cy="12" r="9" /><path d="M8.5 12l2.5 2.5 4.5-5" /></svg>}
                      {k.icon === "warn" && <svg {...S} width={16} height={16} viewBox="0 0 24 24" strokeWidth={1.8} stroke="#B5832F"><path d="M12 3l9.5 17h-19z" /><path d="M12 10v4M12 17.5v.5" /></svg>}
                      {k.icon === "clip" && <svg {...S} width={16} height={16} viewBox="0 0 24 24" strokeWidth={1.8}><rect x="5" y="4" width="14" height="17" rx="2" /><path d="M9 4V3h6v1M9 10h6M9 14h6" /></svg>}
                    </div>
                    <div className="db-kpi-val"><strong>{k.value}</strong><span>{k.sub}</span></div>
                  </div>
                ))}
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
                  <div className="db-pct">
                    <strong>{pct}%</strong>
                    <p>of detected items have a confirmed sorting outcome.</p>
                    <small>Outcome tracking, not classifier accuracy.</small>
                  </div>

                  <div>
                    <div className="db-chart-title">Sorting outcomes</div>
                    <div className="db-axis-label">Items</div>
                    <div className="db-chart">
                      {ticks.map((t, i) => (
                        <div key={t} className={`db-tick${i === 0 ? " base" : ""}`} style={{ bottom: `${(i / 6) * 100}%` }} aria-hidden="true">
                          <span>{t}</span><i />
                        </div>
                      ))}
                      <div className="db-bars" role="group" aria-label={`Sorting outcomes: ${R.confirmed} confirmed, ${R.flagged} flagged, ${R.review} to review`}>
                        {OUTCOMES.map((o) => {
                          const v = values[o.key];
                          const on = !filter || filter === o.key;
                          return (
                            <div key={o.key} className="db-bar-col" style={{ opacity: on ? 1 : 0.35 }}>
                              <span className="db-bar-val">{v}</span>
                              <button
                                type="button"
                                className="db-bar"
                                aria-pressed={filter === o.key}
                                aria-label={`${o.label}: ${v} items. Show these in recent detections`}
                                onClick={() => { setFilter(filter === o.key ? null : o.key); setOpen(null); }}
                                style={{ height: `${(v / max) * 100}%`, background: o.color }}
                              />
                            </div>
                          );
                        })}
                      </div>
                    </div>
                    <div className="db-bar-labels">
                      {OUTCOMES.map((o) => <span key={o.key} style={{ opacity: !filter || filter === o.key ? 1 : 0.35 }}>{o.label}</span>)}
                    </div>
                    <p className="db-foot">{R.total} items total · {R.long} · Demo data</p>
                  </div>
                </div>
              </section>
            </div>
          </div>

          <footer className="db-footer">
            <span>Cashcan · Thoughtful sorting, one item at a time.</span>
            <span>Demo data · Metro Vancouver · All times local</span>
          </footer>
        </div>
      </main>
    </div>
  );
}
