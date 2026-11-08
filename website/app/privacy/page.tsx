import type { Metadata } from "next";
import PageShell from "@/components/PageShell";
import { PRIVACY } from "@/lib/content";

export const metadata: Metadata = { title: "Privacy — CashCan", description: "What CashCan stores about you and what it never keeps." };

export default function PrivacyPage() {
  return (
    <PageShell eyebrow="Privacy" title="Why a face, and what we keep." lede="Face match ties each reward to one real person, without a card or a phone. It is opt-in, and here is exactly what happens to your data.">
      <ul className="priv-list page-priv">
        {PRIVACY.map(([title, body]) => (
          <li key={title}><span><b>{title}</b><small>{body}</small></span></li>
        ))}
      </ul>

      <section className="price-rules" aria-label="Details">
        <h2>The details</h2>
        <ul>
          <li><b>What we store.</b> Your login (through Auth0), your wallet address, and a numeric face template of 512 numbers made from your enrollment photos. That is all.</li>
          <li><b>What we never keep.</b> The photos themselves. They are used once to make the template and then discarded. A stranger at a bin is not identified and no face data is kept for them.</li>
          <li><b>What we log.</b> Match results (a similarity score and whether it matched) and the items you sort, so the dashboard can show your activity. The logs contain no face data.</li>
          <li><b>One face, one account.</b> A face that is already registered cannot be enrolled on a second account.</li>
          <li><b>Liveness.</b> The bin asks you to turn your head so a still photo on a screen cannot collect your rewards. It does not stop a recorded video of you, a 3D mask or a deepfake, and we do not claim it does.</li>
          <li><b>Where it lives.</b> Face templates and activity are stored in Databricks. Login is handled by Auth0.</li>
          <li><b>Deleting your data.</b> Self-service deletion is not built yet. Ask the CashCan team and we will delete your face template and account.</li>
        </ul>
        <p className="page-note">This is a hackathon prototype. Payouts use Solana devnet test tokens only.</p>
      </section>
    </PageShell>
  );
}
