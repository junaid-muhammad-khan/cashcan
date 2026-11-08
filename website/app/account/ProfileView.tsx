"use client";

import Link from "next/link";
import { AppFooter, AppHeader } from "@/components/AppChrome";
import type { Me } from "@/lib/faceApi";
import "../dashboard/dashboard.css";

// The Profile tab of the signed-in app: same header and footer as the dashboard.
export default function ProfileView({ name, email, firstName, me, welcome }: { name?: string; email?: string; firstName: string; me: Me | null; welcome: boolean }) {
  return (
    <div className="db">
      <AppHeader current="profile" />
      <main className="db-wrap">
        <div className="db-inner db-profile">
          {welcome && <div className="db-welcome" role="status">Your account is ready.</div>}
          <div className="db-greet">
            <div>
              <h1>{welcome ? `Welcome to CashCan, ${firstName}.` : `${firstName}'s profile`}</h1>
              <p>Your details and where your rewards go.</p>
            </div>
          </div>

          <section className="db-card db-profile-card" aria-label="Account details">
            <dl>
              <dt>Name</dt><dd>{name}</dd>
              <dt>Email</dt><dd>{email}</dd>
              <dt>Wallet</dt>
              <dd>
                {me?.sol_wallet ? <span className="db-mono">{me.sol_wallet}</span> : "Not linked yet"}
                {" "}<Link href="/dashboard#redeem" className="db-inline-link">{me?.sol_wallet ? "Change" : "Add a wallet"}</Link>
              </dd>
              <dt>Face match</dt><dd>{me?.face_enrolled ? "Set up. Any CashCan bin can recognise you." : "Not set up"}</dd>
            </dl>
          </section>

          <AppFooter note="Payouts use Solana devnet test tokens only" />
        </div>
      </main>
    </div>
  );
}
