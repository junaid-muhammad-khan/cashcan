"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import Field from "@/components/Field";
import PasswordStrength from "@/components/PasswordStrength";
import { validatePassword } from "@/lib/validation";

export default function ResetForm() {
  const router = useRouter();
  const token = useSearchParams().get("token") ?? "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [errors, setErrors] = useState<{ password?: string; confirm?: string }>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!token) {
    return (
      <>
        <h1>This link is incomplete</h1>
        <p className="sub">Open the reset link from your email again, or request a new one.</p>
        <div className="cta-row" style={{ marginTop: 24 }}>
          <Link href="/forgot-password" className="btn btn-primary">Request a new link</Link>
        </div>
      </>
    );
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const next = {
      password: validatePassword(password, true),
      confirm: confirm === password ? undefined : "The two passwords don't match. Type the same one in both boxes.",
    };
    setErrors(next);
    if (next.password || next.confirm) return;
    setBusy(true);
    setFormError(null);
    try {
      const res = await fetch("/api/auth/reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, password }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        if (data.fieldErrors?.password) setErrors({ password: data.fieldErrors.password });
        else setFormError(data.error ?? "We couldn't change your password just now. Try again in a moment.");
        return;
      }
      router.push("/dashboard");
      router.refresh();
    } catch {
      setFormError("We couldn't reach CashCan. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h1>Choose a new password</h1>
      <p className="sub">You&apos;ll be logged in as soon as it&apos;s saved.</p>
      <form className="form" onSubmit={onSubmit} noValidate>
        {formError && (
          <div className="alert" role="alert">
            {formError} <Link href="/forgot-password">Request a new link</Link>
          </div>
        )}
        <Field
          id="password" label="New password" hint="8+ characters" type="password" autoComplete="new-password" value={password} error={errors.password}
          onChange={(v) => { setPassword(v); if (errors.password) setErrors((x) => ({ ...x, password: undefined })); }}
          onBlur={() => password && setErrors((x) => ({ ...x, password: validatePassword(password, true) }))}
        >
          <PasswordStrength password={password} />
        </Field>
        <Field
          id="confirm" label="Confirm new password" type="password" autoComplete="new-password" value={confirm} error={errors.confirm}
          onChange={(v) => { setConfirm(v); if (errors.confirm) setErrors((x) => ({ ...x, confirm: undefined })); }}
        />
        <button type="submit" className="btn btn-primary" disabled={busy}>{busy ? "Saving…" : "Save new password"}</button>
      </form>
    </>
  );
}
