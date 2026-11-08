"use client";

import { useAuth0 } from "@auth0/auth0-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect } from "react";
import RequireFace from "@/components/RequireFace";
import type { Me } from "@/lib/faceApi";
import SiteFooter from "@/components/SiteFooter";
import SiteNav from "@/components/SiteNav";

export default function AccountPage() {
  return (
    <Suspense>
      <AccountPageInner />
    </Suspense>
  );
}

function AccountPageInner() {
  return <RequireFace>{({ me }) => <AccountBody me={me} />}</RequireFace>;
}

function AccountBody({ me }: { me: Me | null }) {
  const { isLoading, isAuthenticated, user, loginWithRedirect, logout } = useAuth0();
  const welcome = useSearchParams().get("welcome");

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      loginWithRedirect({ appState: { returnTo: "/account" } });
    }
  }, [isLoading, isAuthenticated, loginWithRedirect]);

  if (isLoading || !isAuthenticated || !user) return null;

  const firstName = (user.given_name ?? user.name ?? user.email ?? "there").split(" ")[0];

  return (
    <>
    <div style={{ padding: "0 24px 96px" }}>
      <SiteNav />
      <main className="container" style={{ maxWidth: 720, marginTop: 48 }}>
        <div className="eyebrow">{welcome ? "Account created" : "Your account"}</div>
        <h1 style={{ fontSize: 44, marginTop: 12 }}>
          {welcome ? `Welcome to CashCan, ${firstName}.` : `Hi, ${firstName}.`}
        </h1>
        <p className="section-lede">Add your crypto wallet address so we know where to send your SOL.</p>

        <section className="account-card" aria-label="Account details">
          <dl>
            <dt>Name</dt><dd>{user.name}</dd>
            <dt>Email</dt><dd>{user.email}</dd>
            <dt>Wallet</dt><dd>{me?.sol_wallet ?? "Not linked yet"}</dd>
            <dt>Face match</dt><dd>{me?.face_enrolled ? "Set up" : "Not set up"}</dd>
          </dl>
        </section>

        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: 28 }}>
          <a href="/dashboard" className="btn btn-primary">Back to dashboard</a>
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => logout({ logoutParams: { returnTo: window.location.origin } })}
          >
            Log out
          </button>
        </div>
      </main>
    </div>
    <SiteFooter />
    </>
  );
}
