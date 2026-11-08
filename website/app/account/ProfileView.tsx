"use client";

import Link from "next/link";
import { useState } from "react";
import { AppFooter, AppHeader } from "@/components/AppChrome";
import type { Me } from "@/lib/faceApi";
import "../dashboard/dashboard.css";

const SOLANA_RE = /^[1-9A-HJ-NP-Za-km-z]{32,44}$/;

// The Profile tab of the signed-in app: same header and footer as the dashboard.
// This is the one place a wallet address is collected — /enroll just links here if it's missing.
export default function ProfileView({ name, email, firstName, me, onSaveWallet, welcome }: {
  name?: string; email?: string; firstName: string; me: Me | null; onSaveWallet?: (wallet: string) => Promise<unknown>; welcome: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [walletErr, setWalletErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function saveWallet() {
    const w = draft.trim();
    if (!SOLANA_RE.test(w)) { setWalletErr("Solana addresses are 32–44 letters and numbers. Paste it again."); return; }
    setSaving(true); setWalletErr(null);
    try { await onSaveWallet?.(w); setEditing(false); } catch (e) { setWalletErr((e as Error).message); }
    setSaving(false);
  }

  return (
    <div className="db">
      <AppHeader current="profile" />
      <main className="db-wrap">
        <div className="db-inner db-profile">
          {welcome && <div className="db-welcome" role="status">Your account is ready.</div>}
          <div className="db-greet">
            <div>
              <h1>{welcome ? `Welcome to CashCan, ${firstName}.` : `${firstName}'s profile`}</h1>
              <p>Your details and where your rewards go.</p>
            </div>
          </div>

          <section className="db-card db-profile-card" aria-label="Account details">
            <dl>
              <dt>Name</dt><dd>{name}</dd>
              <dt>Email</dt><dd>{email}</dd>
              <dt>Wallet</dt>
              <dd>
                {editing ? (
                  <div style={{ marginTop: 6 }}>
                    <label htmlFor="profile-wallet-input" className="sr-only">Solana wallet address</label>
                    <input id="profile-wallet-input" type="text" value={draft} onChange={(e) => setDraft(e.target.value)} spellCheck={false} autoComplete="off"
                      placeholder="Paste your Solana wallet address"
                      style={{ width: "100%", maxWidth: 420, padding: "9px 10px", borderRadius: 8, border: "1px solid #36574a", background: "#17352a", color: "#fff", fontFamily: "monospace", fontSize: 12 }} />
                    {walletErr && <p role="alert" className="db-small" style={{ color: "#ffb4a8" }}>{walletErr}</p>}
                    <div style={{ display: "flex", gap: 10, marginTop: 10 }}>
                      <button type="button" className="db-lime" disabled={saving} onClick={saveWallet}>{saving ? "Saving…" : "Save wallet"}</button>
                      <button type="button" className="db-lime" onClick={() => { setEditing(false); setWalletErr(null); }}>Cancel</button>
                    </div>
                  </div>
                ) : (
                  <>
                    {me?.sol_wallet ? <span className="db-mono">{me.sol_wallet}</span> : "Not linked yet"}
                    {" "}
                    <button type="button" className="db-inline-link" style={{ background: "none", border: 0, padding: 0, cursor: "pointer", font: "inherit", color: "inherit", textDecoration: "underline" }}
                      onClick={() => { setDraft(me?.sol_wallet ?? ""); setEditing(true); }}>
                      {me?.sol_wallet ? "Change" : "Add a wallet"}
                    </button>
                  </>
                )}
              </dd>
              <dt>Face match</dt><dd>{me?.face_enrolled ? "Set up. Any CashCan bin can recognise you." : "Not set up"}</dd>
            </dl>
            {!me?.sol_wallet && !me?.face_enrolled && (
              <p className="db-small" style={{ marginTop: 14 }}>
                Add a wallet above, then <Link href="/enroll" className="db-inline-link">set up face match</Link> to start earning.
              </p>
            )}
          </section>

          <AppFooter note="Payouts use Solana devnet test tokens only" />
        </div>
      </main>
    </div>
  );
}
