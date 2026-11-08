import type { Metadata } from "next";
import AuthShell from "@/components/AuthShell";
import ForgotForm from "./ForgotForm";

export const metadata: Metadata = { title: "Reset your password — CashCan" };

export default function ForgotPasswordPage() {
  return (
    <AuthShell heading="Locked out? It happens." body="We'll get you back to your rewards in a minute. Your wallet and drop history are safe.">
      <ForgotForm />
    </AuthShell>
  );
}
