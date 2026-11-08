"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import Field from "@/components/Field";
import { validateEmail, validatePassword } from "@/lib/validation";

export default function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<{ email?: string; password?: string }>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const next = { email: validateEmail(email), password: validatePassword(password, false) };
    setErrors(next);
    if (next.email || next.password) return;
    setBusy(true);
    setFormError(null);
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setFormError(data.error ?? "We couldn't log you in just now. Try again in a moment.");
        return;
      }
      const dest = params.get("next");
      router.push(dest && dest.startsWith("/") && !dest.startsWith("//") ? dest : "/account");
      router.refresh();
    } catch {
      setFormError("We couldn't reach CashCan. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h1>Welcome back</h1>
      <p className="sub">Log in to see your drops, rewards and wallet.</p>
      <form className="form" onSubmit={onSubmit} noValidate>
        {formError && <div className="alert" role="alert">{formError}</div>}
        <Field
          id="email" label="Email" type="email" autoComplete="email" value={email} error={errors.email}
          onChange={(v) => { setEmail(v); if (errors.email) setErrors((x) => ({ ...x, email: undefined })); }}
          onBlur={() => email && setErrors((x) => ({ ...x, email: validateEmail(email) }))}
        />
        <Field
          id="password" label="Password" type="password" autoComplete="current-password" value={password} error={errors.password}
          onChange={(v) => { setPassword(v); if (errors.password) setErrors((x) => ({ ...x, password: undefined })); }}
        />
        <button type="submit" className="btn btn-primary" disabled={busy}>{busy ? "Logging in…" : "Log in"}</button>
      </form>
      <p className="auth-switch">New to CashCan? <Link href="/signup">Create an account</Link></p>
    </>
  );
}
