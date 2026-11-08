import type { Metadata } from "next";
import { Suspense } from "react";
import AuthShell from "@/components/AuthShell";
import ResetForm from "./ResetForm";

export const metadata: Metadata = { title: "Choose a new password — CashCan", referrer: "no-referrer" };

export default function ResetPasswordPage() {
  return (
    <AuthShell heading="Almost back in." body="Pick a new password and you'll go straight to your account.">
      <Suspense>
        <ResetForm />
      </Suspense>
    </AuthShell>
  );
}
