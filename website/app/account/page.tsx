"use client";

import { useAuth0 } from "@auth0/auth0-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect } from "react";
import RequireFace from "@/components/RequireFace";
import type { Me } from "@/lib/faceApi";
import ProfileView from "./ProfileView";

export default function AccountPage() {
  return (
    <Suspense>
      <RequireFace>{({ me }) => <ProfileBody me={me} />}</RequireFace>
    </Suspense>
  );
}

function ProfileBody({ me }: { me: Me | null }) {
  const { isLoading, isAuthenticated, user, loginWithRedirect } = useAuth0();
  const welcome = useSearchParams().get("welcome");

  useEffect(() => {
    if (!isLoading && !isAuthenticated) loginWithRedirect({ appState: { returnTo: "/account" } });
  }, [isLoading, isAuthenticated, loginWithRedirect]);

  if (isLoading || !isAuthenticated || !user) return null;
  const firstName = (user.given_name ?? user.name ?? user.email ?? "there").split(" ")[0];
  return <ProfileView name={user.name} email={user.email} firstName={firstName} me={me} welcome={!!welcome} />;
}
