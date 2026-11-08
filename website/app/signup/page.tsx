"use client";

import { useAuth0 } from "@auth0/auth0-react";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import AuthPanel from "@/components/AuthPanel";
import AuthShell from "@/components/AuthShell";

const STEPS = [
  { title: "Create your account", sub: "Signed up and verified through Auth0" },
  { title: "Link a Solana wallet", sub: "Where your rewards are sent" },
  { title: "Enroll your face at a bin", sub: "Optional, so no card or phone is needed" },
];

function Journey() {
  return (
    <ol className="journey" aria-label="What happens after you sign up">
      {STEPS.map((s, i) => (
        <li key={s.title}>
          <span className="mark" aria-hidden="true">{i + 1}</span>
          <span>
            <b>{s.title}</b>
            <small>{s.sub}</small>
          </span>
        </li>
      ))}
    </ol>
  );
}

export default function SignupPage() {
  const { isLoading, isAuthenticated } = useAuth0();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && isAuthenticated) router.replace("/dashboard");
  }, [isLoading, isAuthenticated, router]);

  if (isLoading || isAuthenticated) return null;

  return (
    <AuthShell
      heading="Every item you sort right pays you back."
      body="Three steps and the next CashCan bin knows where to send your rewards."
      aside={<Journey />}
    >
      <AuthPanel mode="signup" returnTo="/dashboard?welcome=1" />
    </AuthShell>
  );
}
