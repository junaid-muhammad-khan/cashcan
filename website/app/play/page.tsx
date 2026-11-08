"use client";

import { useAuth0 } from "@auth0/auth0-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect } from "react";
import { useProfile } from "@/lib/useProfile";
import PlayView from "./PlayView";

// The sorting game for kids. Needs a login (so scores belong to someone) but, unlike /dashboard, not face match or a wallet.
export default function PlayPage() {
  return (
    <Suspense>
      <PlayBody />
    </Suspense>
  );
}

// Local dev only: /play?preview=1 plays without logging in (scores can't be saved). Never works on the live site.
const DEV_PREVIEW = process.env.NODE_ENV === "development";

function PlayBody() {
  const asked = useSearchParams().get("preview") === "1";
  const preview = DEV_PREVIEW && asked;
  return preview ? <PlayView getToken={null} nickname={null} /> : <SignedIn />;
}

function SignedIn() {
  const { isLoading, isAuthenticated, user, loginWithRedirect } = useAuth0();
  const { state, getToken } = useProfile();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) loginWithRedirect({ appState: { returnTo: "/play" } });
  }, [isLoading, isAuthenticated, loginWithRedirect]);

  if (isLoading || !isAuthenticated || !user) return null;
  return <PlayView getToken={getToken} nickname={state.status === "ready" ? state.me.pseudonym ?? null : null} />;
}
