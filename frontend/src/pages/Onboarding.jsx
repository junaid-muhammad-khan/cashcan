import { useState } from "react";
import { api } from "../api.js";

const STEPS = [
  ["consent", "Consent"],
  ["face", "Face scan"],
  ["wallet", "Wallet"],
];

export default function Onboarding({ me, onChange }) {
  const done = me.onboarding;
  const current = STEPS.find(([k]) => !done[k])?.[0] ?? "wallet";
  const [name, setName] = useState(me.user.display_name || "");
  const [agreed, setAgreed] = useState(false);
  const [addr, setAddr] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const run = async (fn) => {
    setErr(""); setBusy(true);
    try {
      const r = await fn();
      onChange({ onboarding: r.onboarding, ...(r.user ? { user: r.user } : {}) });
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  };

  return (
    <div className="narrow">
      <h2>Set up your account</h2>
      <ol className="steps">
        {STEPS.map(([k, label], i) => (
          <li key={k} className={done[k] ? "done" : k === current ? "active" : ""}>
            <span className="dot">{done[k] ? "✓" : i + 1}</span>{label}
          </li>
        ))}
      </ol>

      <div className="card">
        {current === "consent" && (
          <>
            <h3>Face enrollment consent</h3>
            <p>The bin recognizes you by your face so rewards go to the right wallet. We store a numeric
              face <b>embedding</b> only, never your photo. You can ask us to delete it at any time.</p>
            <label className="field">Display name (shown on the leaderboard if you opt in)
              <input value={name} maxLength={40} onChange={(e) => setName(e.target.value)} />
            </label>
            <label className="check">
              <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} />
              I agree to face enrollment as described.
            </label>
            <button className="btn primary" disabled={!agreed || busy}
              onClick={() => run(() => api("/onboarding/consent", { method: "POST", data: { agreed, display_name: name } }))}>
              Continue
            </button>
          </>
        )}

        {current === "face" && (
          <>
            <h3>Scan your face</h3>
            <div className="camera">Camera capture goes here<br /><span className="tiny">(stub: next iteration)</span></div>
            <button className="btn primary" disabled={busy}
              onClick={() => run(() => api("/onboarding/face", { method: "POST" }))}>
              Simulate scan
            </button>
          </>
        )}

        {current === "wallet" && (
          <>
            <h3>Link your Solana wallet</h3>
            <p>Paste your <b>public</b> wallet address (devnet). Never enter a seed phrase or private key.</p>
            <label className="field">Wallet address
              <input value={addr} placeholder="e.g. 7xKX…" onChange={(e) => setAddr(e.target.value)} />
            </label>
            <button className="btn primary" disabled={!addr || busy}
              onClick={() => run(() => api("/onboarding/wallet", { method: "POST", data: { address: addr } }))}>
              Finish
            </button>
            <p className="tiny muted">Ownership verification (signed message) is not implemented yet.</p>
          </>
        )}
        {err && <p className="error">{err}</p>}
      </div>
    </div>
  );
}
