type Bin = "cans" | "organics" | "waste";
// Illustrative example drops for the hero mockup — not live data, labelled "example" in the UI.
const EVENTS: { item: string; detail: string; bin: Bin; pay: number }[] = [
  { item: "Aluminum can", detail: "Clean · wallet ••7Qx", bin: "cans", pay: 0.004 },
  { item: "Banana peel", detail: "Clean · organics", bin: "organics", pay: 0.001 },
  { item: "Greasy plastic tray", detail: "Contaminated · 25% reward", bin: "cans", pay: 0.0005 },
  { item: "Chip bag", detail: "Not reward-eligible", bin: "waste", pay: 0 },
];
const SHORT: Record<Bin, string> = { cans: "CAN", organics: "ORG", waste: "WST" };

export default function LiveFeed() {
  return (
    <>
      <div className="feed-head"><span>Example drops</span><small>illustrative, not live data</small></div>
      <ul className="feed" aria-live="off">
        {EVENTS.map((r) => (
          <li key={r.item}>
            <span className={`bin-chip bin-${r.bin}`}>{SHORT[r.bin]}</span>
            <span className="meta"><b>{r.item}</b><small>{r.detail}</small></span>
            <span className={r.pay ? "pay" : "pay none"}>{r.pay ? `+${r.pay} SOL` : "—"}</span>
          </li>
        ))}
      </ul>
    </>
  );
}
