"use client";

import { useAuth0 } from "@auth0/auth0-react";
import { useEffect } from "react";
import AuthShell from "@/components/AuthShell";

export default function SignupPage() {
  const { isLoading, isAuthenticated, loginWithRedirect } = useAuth0();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      loginWithRedirect({
        authorizationParams: { screen_hint: "signup" },
        appState: { returnTo: "/account?welcome=1" },
      });
    }
  }, [isLoading, isAuthenticated, loginWithRedirect]);

  return (
    <AuthShell
      heading="Every item you sort right pays you back."
      body="Three steps and the next CashCan bin knows where to send your rewards."
    >
      <h1>Create your account</h1>
      <p className="sub">Taking you to sign up…</p>
    </AuthShell>
  );
}
