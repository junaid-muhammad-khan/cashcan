import type { Metadata } from "next";
import Link from "next/link";
import PageShell from "@/components/PageShell";
import { GATES, STEPS } from "@/lib/content";

export const metadata: Metadata = { title: "How it works — CashCan", description: "How an item flows from your hand to a payout." };

export default function HowItWorksPage() {
  return (
    <PageShell eyebrow="How it works" title="Five seconds from drop to payout." lede="Here is what happens when you step up to a CashCan bin.">
      <ol className="how-list">
        {STEPS.map((s, i) => (
          <li key={s.title}>
            <span className="how-num">0{i + 1}</span>
            <div><h2>{s.title}</h2><p>{s.body}</p></div>
          </li>
        ))}
      </ol>

      <section className="price-rules" aria-label="The checks before a payout">
        <h2>The checks before anything is paid</h2>
        <ul>{GATES.map(([label, val]) => <li key={label}><b>{label}.</b> For example: {val}.</li>)}</ul>
        <p className="page-note">The example values are illustrative. The bin always opens the right lid; the checks decide only whether a reward is paid.</p>
      </section>

      <div className="cta-row" style={{ marginTop: 28 }}>
        <Link href="/prices" className="btn btn-primary">See what items earn</Link>
        <Link href="/local-rules" className="btn btn-ghost">Local rules</Link>
      </div>
    </PageShell>
  );
}
