import type { Metadata } from "next";
import Link from "next/link";
import PageShell from "@/components/PageShell";

export const metadata: Metadata = { title: "Local rules — CashCan", description: "Why CashCan sorts by your city's rules, and the three bins." };

const BINS = [
  ["Cans", "Drink containers that take a deposit (metal, plastic or glass). These are the items that can earn a reward."],
  ["Organics", "Food scraps and other compostable items."],
  ["Waste", "Everything else. It is sorted and counted, but does not earn a reward."],
];

export default function LocalRulesPage() {
  return (
    <PageShell eyebrow="Local rules" title="Your city's rules, not a material label." lede="Sorting rules are local and confusing. An item labelled compostable may still not be accepted in your green bin.">
      <div className="three" style={{ marginTop: 28 }}>
        {BINS.map(([name, body]) => (
          <article className="card" key={name}><h3>{name}</h3><p>{body}</p></article>
        ))}
      </div>
      <section className="price-rules" aria-label="Where the rules come from">
        <h2>Where the rules come from</h2>
        <ul>
          <li><b>One decision, three bins.</b> The bin has three openings. Every item is classified into one of them, and the matching lid opens whether or not anyone is signed in.</li>
          <li><b>Metro Vancouver first.</b> We are building the rule table for Metro Vancouver and checking it against the current Recycle BC and Metro Vancouver accepted-materials lists. Until that check is done, treat the bin&apos;s advice as a guide, not the final word.</li>
          <li><b>A reason you can read.</b> When the bin decides, it shows a short plain-language reason on its screen.</li>
        </ul>
      </section>
      <div className="cta-row" style={{ marginTop: 28 }}>
        <Link href="/how-it-works" className="btn btn-primary">How it works</Link>
        <Link href="/prices" className="btn btn-ghost">Prices</Link>
      </div>
    </PageShell>
  );
}
