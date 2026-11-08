import type { Metadata } from "next";
import Link from "next/link";
import ContainerArt from "@/components/ContainerArt";
import PageShell from "@/components/PageShell";
import RewardCalculator from "@/components/RewardCalculator";
import { CONTAINERS, OTHER, formatCents } from "@/lib/prices";
import { getRewardTable } from "@/lib/rewards";
import "./catalogue.css";

export const metadata: Metadata = { title: "Prices — CashCan", description: "What CashCan pays for each container you sort: half the BC deposit, as cash back." };

// Amounts come from the face API's reward table (the same one the bins are paid from), refreshed every few minutes.
export const revalidate = 300;

export default async function PricesPage() {
  const { table } = await getRewardTable();
  const cans = table.classes.cans ?? 0;
  const otherCents = (id: string, fallback: number | null) => (id in table.classes ? table.classes[id] : fallback);
  return (
    <PageShell
      eyebrow="Prices"
      title="What each container earns."
      lede="Drop a deposit container in the right opening at a CashCan bin and you get half its BC deposit back as cash back, straight to your wallet."
    >
      <ul className="cat-grid">
        {CONTAINERS.map((c) => (
          <li className="cat-card" key={c.id}>
            <div className="cat-head">
              <span className="cat-art"><ContainerArt icon={c.icon} /></span>
              <span>
                <h2>{c.name}</h2>
                <p className="cat-prep">{c.prep}</p>
              </span>
            </div>

            <dl className="cat-cols">
              <div><dt>Size</dt><dd className="cat-size">{c.size}</dd></div>
              <div><dt>BC deposit</dt><dd className="cat-deposit">{c.depositCents}¢</dd></div>
              <div><dt>Cash back</dt><dd><span className="cat-cash">{cans}¢</span></dd></div>
            </dl>

            <details className="cat-more">
              <summary>More info</summary>
              <div className="cat-more-body">
                <p><b>What counts:</b> {c.examples}</p>
                <p><b>Where it goes:</b> the Cans opening. The bin lights it up when it sees the container.</p>
                <p><b>How to bring it:</b> {c.prep.toLowerCase()}, and empty.</p>
              </div>
            </details>
          </li>
        ))}
      </ul>

      <RewardCalculator cashBackCents={cans} />

      <h2 className="cat-subhead">Everything else the bin sorts</h2>
      <ul className="cat-other">
        {OTHER.map((o) => {
          const cents = otherCents(o.id, o.cents);
          return (
            <li key={o.id}>
              <span><b>{o.name}</b><small>Goes in {o.bin}. {o.note}</small></span>
              <span className={`cat-other-price${cents ? "" : " muted"}`}>{formatCents(cents)}</span>
            </li>
          );
        })}
      </ul>

      <section className="price-rules" aria-label="How rewards work">
        <h2>How rewards work</h2>
        <ul>
          <li><b>Half the deposit.</b> Cash back is {Math.round(table.cash_back_share * 100)}% of the BC deposit on that container, the same for every container type.</li>
          <li><b>Paid in SOL right away.</b> The cash back is converted to SOL at the live SOL/CAD price at the moment it is sent to your wallet.</li>
          <li><b>No wallet yet?</b> Your rewards are held and paid as soon as you add a wallet to your account.</li>
          <li><b>Face match first.</b> The reward goes to the person the bin recognises, so you need an account with face match set up.</li>
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
