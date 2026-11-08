"use client";

import { useAuth0 } from "@auth0/auth0-react";
import { useEffect } from "react";
import EnrollFlow from "./EnrollFlow";
import "./enroll.css";

// Face enrollment, right after sign-up. Signed-in only (Auth0 SPA SDK, client-side gate).
export default function EnrollPage() {
  const { isLoading, isAuthenticated, loginWithRedirect } = useAuth0();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) loginWithRedirect({ appState: { returnTo: "/enroll" } });
  }, [isLoading, isAuthenticated, loginWithRedirect]);

  if (isLoading || !isAuthenticated) return null;
  return <EnrollFlow />;
}
