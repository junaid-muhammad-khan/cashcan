"use client";

import { useAuth0 } from "@auth0/auth0-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect } from "react";
import DashboardView from "./DashboardView";
import "./dashboard.css";

// Auth is client-side (Auth0 SPA SDK), so this page gates in an effect, like /account.
export default function DashboardPage() {
  return (
    <Suspense>
      <DashboardPageInner />
    </Suspense>
  );
}

function DashboardPageInner() {
  const { isLoading, isAuthenticated, user, loginWithRedirect } = useAuth0();
  const welcome = useSearchParams().get("welcome") === "1";

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      loginWithRedirect({ appState: { returnTo: "/dashboard" } });
    }
  }, [isLoading, isAuthenticated, loginWithRedirect]);

  if (isLoading || !isAuthenticated || !user) return null;

  const firstName = (user.given_name ?? user.name ?? user.email ?? "there").split(/[\s@]/)[0];

  // Wallet linking has no store yet under Auth0 (see README), so it shows as not connected.
  return <DashboardView firstName={firstName} walletAddress={null} welcome={welcome} />;
}
