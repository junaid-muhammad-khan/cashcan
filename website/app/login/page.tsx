import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { Suspense } from "react";
import AuthShell from "@/components/AuthShell";
import { getCurrentUser } from "@/lib/auth";
import LoginForm from "./LoginForm";

export const metadata: Metadata = { title: "Log in — CashCan" };

export default async function LoginPage() {
  if (await getCurrentUser()) redirect("/dashboard");
  return (
    <AuthShell
      heading="Sort it right. Get paid for it."
      body="Your rewards, drop history and wallet live in your CashCan account."
    >
      <Suspense>
        <LoginForm />
      </Suspense>
    </AuthShell>
  );
}
