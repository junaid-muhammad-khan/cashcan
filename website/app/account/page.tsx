import type { Metadata } from "next";
import { redirect } from "next/navigation";
import SiteNav from "@/components/SiteNav";
import { getCurrentUser } from "@/lib/auth";

export const metadata: Metadata = { title: "Your account — CashCan" };

export default async function AccountPage({ searchParams }: { searchParams: Promise<{ welcome?: string }> }) {
  const user = await getCurrentUser();
  if (!user) redirect("/login?next=/account");
  const { welcome } = await searchParams;

  return (
    <div style={{ padding: "0 24px 96px" }}>
      <SiteNav signedInName={user.name} />
      <main className="container" style={{ maxWidth: 720, marginTop: 48 }}>
        <div className="eyebrow">{welcome ? "Account created" : "Your account"}</div>
        <h1 style={{ fontSize: 44, marginTop: 12 }}>
          {welcome ? `Welcome to CashCan, ${user.name.split(" ")[0]}.` : `Hi, ${user.name.split(" ")[0]}.`}
        </h1>
        <p className="section-lede">
          {user.walletAddress
            ? "Your wallet is linked. Drop a reward-eligible item at any CashCan bin to earn."
            : "Add a Solana wallet address so the bin knows where to send your rewards."}
        </p>

        <section className="account-card" aria-label="Account details">
          <dl>
            <dt>Name</dt><dd>{user.name}</dd>
            <dt>Email</dt><dd>{user.email}</dd>
            <dt>Wallet</dt><dd>{user.walletAddress ?? "Not linked yet"}</dd>
            <dt>Face match</dt><dd>{user.faceOptIn ? "Opted in. Enroll at your next bin." : "Not enrolled"}</dd>
          </dl>
        </section>

        <form action="/api/auth/logout" method="post" style={{ marginTop: 28 }}>
          <button type="submit" className="btn btn-ghost">Log out</button>
        </form>
      </main>
    </div>
  );
}
