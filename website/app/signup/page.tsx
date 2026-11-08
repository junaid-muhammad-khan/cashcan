import type { Metadata } from "next";
import { redirect } from "next/navigation";
import AuthShell from "@/components/AuthShell";
import { getCurrentUser } from "@/lib/auth";
import SignupForm from "./SignupForm";

export const metadata: Metadata = { title: "Sign up — CashCan" };

export default async function SignupPage() {
  if (await getCurrentUser()) redirect("/account");
  return (
    <AuthShell
      heading="Every item you sort right pays you back."
      body="Create an account, link your Solana wallet, and the next CashCan bin will know where to send your rewards."
    >
      <SignupForm />
    </AuthShell>
  );
}
