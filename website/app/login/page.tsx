"use client";

import { useAuth0 } from "@auth0/auth0-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect } from "react";
import AuthShell from "@/components/AuthShell";

export default function LoginPage() {
  return (
    <Suspense>
      <LoginPageInner />
    </Suspense>
  );
}

function LoginPageInner() {
  const { isLoading, isAuthenticated, loginWithRedirect } = useAuth0();
  const next = useSearchParams().get("next");

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      loginWithRedirect({ appState: { returnTo: next && next.startsWith("/") && !next.startsWith("//") ? next : "/account" } });
    }
  }, [isLoading, isAuthenticated, loginWithRedirect, next]);

  return (
    <AuthShell
      heading="Sort it right. Get paid for it."
      body="Your rewards, drop history and wallet live in your CashCan account."
    >
      <h1>Welcome back</h1>
      <p className="sub">Taking you to log in…</p>
    </AuthShell>
  );
}
