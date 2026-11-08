import type { Metadata } from "next";
import Link from "next/link";
import PageShell from "@/components/PageShell";
import { PRICES, formatCents } from "@/lib/prices";

export const metadata: Metadata = { title: "Prices — CashCan", description: "What CashCan pays for each item you sort." };

export default function PricesPage() {
  return (
    <PageShell eyebrow="Prices" title="What each item earns." lede="Sort it right at a CashCan bin and the reward goes straight to your wallet. Here is the catalogue.">
      <div className="price-grid" role="list">
        {PRICES.map((p) => (
          <article className="price-card" role="listitem" key={p.id}>
            <div className="price-top">
              <h2>{p.name}</h2>
              <span className={`price-tag${p.cents ? "" : " muted"}`}>{formatCents(p.cents)}</span>
            </div>
            <p className="price-bin">Goes in <b>{p.bin}</b></p>
            <p>{p.note}</p>
          </article>
        ))}
      </div>

      <section className="price-rules" aria-label="How rewards work">
        <h2>How rewards work</h2>
        <ul>
          <li><b>Face match first.</b> The reward goes to the person the bin recognises, so you need an account with face match set up.</li>
          <li><b>Sort it clean.</b> Greasy or food-soiled items still go in the right bin, but earn a reduced reward.</li>
          <li><b>Only when the bin is sure.</b> If the bin is not confident about an item it goes to Waste and earns nothing.</li>
          <li><b>Prototype money.</b> Rewards are paid as Solana devnet test tokens, which have no cash value, and the amounts above are our current plan.</li>
        </ul>
      </section>

      <div className="cta-row" style={{ marginTop: 28 }}>
        <Link href="/signup" className="btn btn-primary">Create free account</Link>
        <Link href="/how-it-works" className="btn btn-ghost">How it works</Link>
      </div>
    </PageShell>
  );
}
