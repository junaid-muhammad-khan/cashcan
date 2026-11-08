"use client";

import Link from "next/link";
import { useState } from "react";
import Field from "@/components/Field";
import { Check } from "@/components/icons";
import { validateEmail } from "@/lib/validation";

export default function ForgotForm() {
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | undefined>();
  const [formError, setFormError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const err = validateEmail(email);
    setError(err);
    if (err) return;
    setBusy(true);
    setFormError(null);
    try {
      const res = await fetch("/api/auth/forgot", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        if (data.fieldErrors?.email) setError(data.fieldErrors.email);
        else setFormError("We couldn't send a reset link just now. Try again in a moment.");
        return;
      }
      setSent(true);
    } catch {
      setFormError("We couldn't reach CashCan. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  }

  if (sent) {
    return (
      <div className="success-panel" role="status">
        <span className="ok-badge"><Check size={26} strokeWidth={2.6} /></span>
        <h1>Check your email</h1>
        <p className="sub">
          If an account exists for <b>{email.trim()}</b>, we&apos;ve sent a link to reset your password. It works for 30 minutes.
        </p>
        <div className="cta-row" style={{ marginTop: 22 }}>
          <Link href="/login" className="btn btn-primary">Back to log in</Link>
          <button type="button" className="btn btn-ghost" onClick={() => setSent(false)}>Use a different email</button>
        </div>
      </div>
    );
  }

  return (
    <>
      <h1>Reset your password</h1>
      <p className="sub">Enter the email you signed up with and we&apos;ll send you a link to choose a new password.</p>
      <form className="form" onSubmit={onSubmit} noValidate>
        {formError && <div className="alert" role="alert">{formError}</div>}
        <Field
          id="email" label="Email" type="email" autoComplete="email" value={email} error={error}
          onChange={(v) => { setEmail(v); if (error) setError(undefined); }}
          onBlur={() => email && setError(validateEmail(email))}
        />
        <button type="submit" className="btn btn-primary" disabled={busy}>{busy ? "Sending link…" : "Send reset link"}</button>
      </form>
      <p className="auth-switch">Remembered it? <Link href="/login">Log in</Link></p>
    </>
  );
}
