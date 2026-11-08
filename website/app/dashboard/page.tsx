"use client";

import { useAuth0 } from "@auth0/auth0-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect } from "react";
import RequireFace from "@/components/RequireFace";
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

// Local dev only: /dashboard?preview=1 shows the dashboard with demo props, skipping login and the face check.
// NODE_ENV is "production" in every deployed build, so this never works on the live site.
const DEV_PREVIEW = process.env.NODE_ENV === "development";

function DashboardPageInner() {
  const { isLoading, isAuthenticated, user, loginWithRedirect } = useAuth0();
  const params = useSearchParams();
  const welcome = params.get("welcome") === "1";
  const preview = DEV_PREVIEW && params.get("preview") === "1";

  useEffect(() => {
    if (preview) return;
    if (!isLoading && !isAuthenticated) {
      loginWithRedirect({ appState: { returnTo: "/dashboard" } });
    }
  }, [preview, isLoading, isAuthenticated, loginWithRedirect]);

  if (preview) return <DashboardView firstName="Preview" walletAddress={null} welcome={false} />;

  if (isLoading || !isAuthenticated || !user) return null;

  const firstName = (user.given_name ?? user.name ?? user.email ?? "there").split(/[\s@]/)[0];

  return (
    <RequireFace>
      {({ me, setWallet }) => <DashboardView firstName={firstName} walletAddress={me?.sol_wallet ?? null} onSaveWallet={setWallet} welcome={welcome} />}
    </RequireFace>
  );
}
