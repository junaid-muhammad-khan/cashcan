"use client";

import { useAuth0 } from "@auth0/auth0-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect } from "react";
import AuthPanel from "@/components/AuthPanel";
import AuthShell from "@/components/AuthShell";

export default function LoginPage() {
  return (
    <Suspense>
      <LoginPageInner />
    </Suspense>
  );
}

function LoginPageInner() {
  const { isLoading, isAuthenticated } = useAuth0();
  const router = useRouter();
  const next = useSearchParams().get("next");
  const returnTo = next && next.startsWith("/") && !next.startsWith("//") ? next : "/account";

  useEffect(() => {
    if (!isLoading && isAuthenticated) router.replace(returnTo);
  }, [isLoading, isAuthenticated, router, returnTo]);

  if (isLoading || isAuthenticated) return null;

  return (
    <AuthShell
      heading="Sort it right. Get paid for it."
      body="Your rewards, drop history and wallet live in your CashCan account."
    >
      <AuthPanel mode="login" returnTo={returnTo} />
    </AuthShell>
  );
}
