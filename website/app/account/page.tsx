"use client";

import { useAuth0 } from "@auth0/auth0-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect } from "react";
import { useProfile } from "@/lib/useProfile";
import ProfileView from "./ProfileView";

// Unlike /dashboard, /account is NOT behind RequireFace: it's where a signed-in user
// sets up their wallet (and sees their face-match status) in the first place, so it
// must stay reachable even before either of those is set — RequireFace would otherwise
// bounce a brand-new user straight back to /enroll with nowhere to add a wallet.
export default function AccountPage() {
  return (
    <Suspense>
      <ProfileBody />
    </Suspense>
  );
}

function ProfileBody() {
  const { isLoading, isAuthenticated, user, loginWithRedirect } = useAuth0();
  const welcome = useSearchParams().get("welcome");
  const { state, setWallet } = useProfile();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) loginWithRedirect({ appState: { returnTo: "/account" } });
  }, [isLoading, isAuthenticated, loginWithRedirect]);

  if (isLoading || !isAuthenticated || !user) return null;
  const firstName = (user.given_name ?? user.name ?? user.email ?? "there").split(" ")[0];
  return (
    <ProfileView
      name={user.name}
      email={user.email}
      firstName={firstName}
      me={state.status === "ready" ? state.me : null}
      onSaveWallet={setWallet}
      welcome={!!welcome}
    />
  );
}
