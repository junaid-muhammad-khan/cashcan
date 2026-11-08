import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { getCurrentUser } from "@/lib/auth";
import SignupForm from "./SignupForm";

export const metadata: Metadata = { title: "Sign up — CashCan" };

export default async function SignupPage() {
  if (await getCurrentUser()) redirect("/account");
  return <SignupForm />;
}
