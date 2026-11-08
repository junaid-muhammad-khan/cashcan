import type { Metadata } from "next";
import PageShell from "@/components/PageShell";

export const metadata: Metadata = { title: "Terms of use — CashCan", description: "Terms for using the CashCan prototype." };

const TERMS = [
  ["A prototype", "CashCan is a HackCamp 2026 prototype. It may change, break or be switched off at any time."],
  ["Test tokens only", "Rewards are paid as Solana devnet test tokens. They have no cash value and cannot be exchanged for money."],
  ["Your account", "You are responsible for your login and for entering a wallet address you control. Check it carefully: a payout to a wrong address cannot be undone."],
  ["Face match is optional and yours", "You can only enroll your own face, and you agree to us creating a face template from your camera to identify you at bins. See the privacy page for what is kept."],
  ["Fair use", "Do not try to collect rewards for items that were not sorted, use someone else's face or a photo of them, or otherwise game the bin. We may refuse or reverse rewards and close accounts that do."],
  ["Sorting advice", "The bin's advice about where an item goes is a guide. The rule table is still being checked against official local lists."],
  ["No warranty", "The prototype is provided as is, with no promise that it is accurate, available or fit for any purpose."],
];

export default function TermsPage() {
  return (
    <PageShell eyebrow="Terms" title="Terms of use." lede="Plain-language terms for the prototype. These are placeholders for the team to review before any public launch; they are not legal advice.">
      <ol className="terms-list">
        {TERMS.map(([title, body]) => <li key={title}><h2>{title}</h2><p>{body}</p></li>)}
      </ol>
    </PageShell>
  );
}
