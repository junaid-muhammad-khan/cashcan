"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import Field from "@/components/Field";
import { validateEmail, validateName, validatePassword, validateWallet, type FieldErrors } from "@/lib/validation";

export default function SignupForm() {
  const router = useRouter();
  const [v, setV] = useState({ name: "", email: "", password: "", wallet: "" });
  const [terms, setTerms] = useState(false);
  const [faceOptIn, setFaceOptIn] = useState(false);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const validators = {
    name: (s: string) => validateName(s),
    email: (s: string) => validateEmail(s),
    password: (s: string) => validatePassword(s, true),
    wallet: (s: string) => validateWallet(s),
  };
  type K = keyof typeof validators;

  const set = (k: K) => (val: string) => {
    setV((x) => ({ ...x, [k]: val }));
    if (errors[k]) setErrors((x) => ({ ...x, [k]: undefined }));
  };
  const blur = (k: K) => () => {
    if (v[k]) setErrors((x) => ({ ...x, [k]: validators[k](v[k]) }));
  };

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const next: FieldErrors = {
      name: validators.name(v.name),
      email: validators.email(v.email),
      password: validators.password(v.password),
      wallet: validators.wallet(v.wallet),
      terms: terms ? undefined : "Accept the terms to create your account.",
    };
    setErrors(next);
    if (Object.values(next).some(Boolean)) return;
    setBusy(true);
    setFormError(null);
    try {
      const res = await fetch("/api/auth/signup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...v, terms, faceOptIn }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        if (data.fieldErrors) setErrors(data.fieldErrors);
        else setFormError(data.error ?? "We couldn't create your account just now. Try again in a moment.");
        return;
      }
      router.push("/account?welcome=1");
      router.refresh();
    } catch {
      setFormError("We couldn't reach CashCan. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h1>Create your account</h1>
      <p className="sub">Free to join. Earn devnet SOL every time you sort right.</p>
      <form className="form" onSubmit={onSubmit} noValidate>
        {formError && <div className="alert" role="alert">{formError}</div>}
        <Field id="name" label="Name" autoComplete="name" value={v.name} error={errors.name} onChange={set("name")} onBlur={blur("name")} />
        <Field id="email" label="Email" type="email" autoComplete="email" value={v.email} error={errors.email} onChange={set("email")} onBlur={blur("email")} />
        <Field id="password" label="Password" hint="8+ characters" type="password" autoComplete="new-password" value={v.password} error={errors.password} onChange={set("password")} onBlur={blur("password")} />
        <Field id="wallet" label="Solana wallet address" hint="optional, add it later" autoComplete="off" value={v.wallet} error={errors.wallet} onChange={set("wallet")} onBlur={blur("wallet")} />

        <label className="check">
          <input type="checkbox" checked={faceOptIn} onChange={(e) => setFaceOptIn(e.target.checked)} />
          <span>I&apos;d like to enroll my face at a bin so rewards reach me without a card or phone. Only a face template is stored, never photos, and I can delete it any time.</span>
        </label>
        <div>
          <label className="check">
            <input
              type="checkbox"
              checked={terms}
              aria-invalid={errors.terms ? true : undefined}
              aria-describedby={errors.terms ? "terms-err" : undefined}
              onChange={(e) => { setTerms(e.target.checked); if (e.target.checked) setErrors((x) => ({ ...x, terms: undefined })); }}
            />
            <span>I agree to the terms and understand payouts are Solana devnet test tokens with no cash value.</span>
          </label>
          {errors.terms && <p className="err" id="terms-err" style={{ color: "var(--danger)", fontSize: 13, marginTop: 6 }}>{errors.terms}</p>}
        </div>

        <button type="submit" className="btn btn-primary" disabled={busy}>{busy ? "Creating account…" : "Create account"}</button>
      </form>
      <p className="auth-switch">Already have an account? <Link href="/login">Log in</Link></p>
    </>
  );
}
