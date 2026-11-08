"use client";

import { useEffect, useState } from "react";

type Bin = "cans" | "organics" | "waste";
// Sample events for the hero mockup — labelled "sample data" in the UI.
const EVENTS: { item: string; detail: string; bin: Bin; pay: number }[] = [
  { item: "Aluminum can", detail: "Clean · wallet ••7Qx", bin: "cans", pay: 0.004 },
  { item: "Banana peel", detail: "Clean · organics", bin: "organics", pay: 0.001 },
  { item: "Greasy plastic tray", detail: "Contaminated · 25% reward", bin: "cans", pay: 0.0005 },
  { item: "Chip bag", detail: "Not reward-eligible", bin: "waste", pay: 0 },
  { item: "Glass bottle", detail: "Clean · Return-It", bin: "cans", pay: 0.002 },
  { item: "Coffee cup", detail: "Low confidence · no payout", bin: "waste", pay: 0 },
];
const SHORT: Record<Bin, string> = { cans: "CAN", organics: "ORG", waste: "WST" };

export default function LiveFeed() {
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const id = setInterval(() => setTick((t) => t + 1), 2400);
    return () => clearInterval(id);
  }, []);

  const rows = [0, 1, 2, 3].map((i) => EVENTS[(tick + EVENTS.length * 4 - i) % EVENTS.length]);

  return (
    <>
      <div className="stat-row">
        <div className="stat"><small>Items today</small><strong>{128 + tick * 2}</strong></div>
        <div className="stat"><small>Clean rate</small><strong>{81 + (tick % 3)}%</strong></div>
        <div className="stat"><small>SOL paid</small><strong>{(0.214 + tick * 0.002).toFixed(3)}</strong></div>
      </div>
      <div className="feed-head"><span>Live drops</span><small>sample data</small></div>
      <ul className="feed" aria-live="off">
        {rows.map((r, i) => (
          <li key={`${tick - i}`} className={i === 0 && tick > 0 ? "fresh" : undefined}>
            <span className={`bin-chip bin-${r.bin}`}>{SHORT[r.bin]}</span>
            <span className="meta"><b>{r.item}</b><small>{r.detail}</small></span>
            <span className={r.pay ? "pay" : "pay none"}>{r.pay ? `+${r.pay} SOL` : "—"}</span>
          </li>
        ))}
      </ul>
    </>
  );
}
