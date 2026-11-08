import { useEffect, useState } from "react";
import { api, sol } from "../api.js";

const BIN_LABEL = { garbage: "Garbage", organics: "Organics", containers: "Containers", paper: "Paper" };
const fmtDate = (iso) => new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });

function Stat({ label, value, sub }) {
  return (
    <div className="card stat">
      <div className="muted tiny">{label}</div>
      <div className="big">{value}</div>
      {sub && <div className="tiny muted">{sub}</div>}
    </div>
  );
}

export default function Dashboard({ me }) {
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => { api("/dashboard").then(setD).catch((e) => setErr(e.message)); }, []);

  if (err) return <p className="error">{err}</p>;
  if (!d) return <p className="muted">Loading…</p>;
  const s = d.stats;
  const max = Math.max(1, ...d.breakdown.map((b) => b.count));

  return (
    <div className="dash">
      <div className="row between">
        <h2>Your dashboard</h2>
        <span className="pill">{d.network}</span>
      </div>

      <div className="grid4">
        <Stat label="SOL earned (confirmed)" value={sol(s.lamports_confirmed)} sub={`+${sol(s.lamports_pending)} pending`} />
        <Stat label="Items sorted" value={s.items_total} />
        <Stat label="Clean rate" value={s.clean_rate == null ? "–" : `${Math.round(s.clean_rate * 100)}%`} sub={`${s.items_contaminated} contaminated`} />
        <Stat label="Wallet" value={<span className="mono small">{me.user.wallet?.slice(0, 4)}…{me.user.wallet?.slice(-4)}</span>}
          sub={me.user.wallet_verified ? "verified" : "not verified yet"} />
      </div>

      <div className="grid2">
        <section className="card">
          <h3>What you sort</h3>
          {d.breakdown.length === 0 && <p className="muted">No items yet.</p>}
          {d.breakdown.map((b) => (
            <div key={b.item} className="bar-row">
              <span>{b.item}</span>
              <div className="bar"><div style={{ width: `${(b.count / max) * 100}%` }} /></div>
              <span className="muted">{b.count}</span>
            </div>
          ))}
        </section>

        <section className="card">
          <h3>Leaderboard</h3>
          <p className="tiny muted">Ranked by clean deposits (metric not final).</p>
          <table>
            <thead><tr><th>#</th><th>Name</th><th className="r">Clean</th><th className="r">SOL</th></tr></thead>
            <tbody>
              {d.leaderboard.map((r) => (
                <tr key={r.rank} className={r.is_me ? "me" : ""}>
                  <td>{r.rank}</td><td>{r.name}</td><td className="r">{r.clean}</td><td className="r">{sol(r.lamports)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>

      <section className="card">
        <h3>Recent activity</h3>
        <table>
          <thead><tr><th>When</th><th>Item</th><th>Went to</th><th>Condition</th><th className="r">Reward</th></tr></thead>
          <tbody>
            {d.recent.map((e) => (
              <tr key={e.id}>
                <td>{fmtDate(e.when)}</td><td>{e.item}</td><td>{BIN_LABEL[e.bin] || e.bin}</td>
                <td>{e.contaminated ? <span className="tag bad">contaminated</span> : <span className="tag ok">clean</span>}</td>
                <td className="r">{e.payout_lamports ? `${sol(e.payout_lamports)} ` : "–"}
                  {e.payout_status && <span className={`tag ${e.payout_status}`}>{e.payout_status}</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="card">
        <h3>Payout history</h3>
        <table>
          <thead><tr><th>When</th><th className="r">SOL</th><th>Status</th><th>Transaction</th></tr></thead>
          <tbody>
            {d.payouts.map((p) => (
              <tr key={p.id}>
                <td>{fmtDate(p.when)}</td><td className="r">{sol(p.lamports)}</td>
                <td><span className={`tag ${p.status}`}>{p.status}</span></td>
                <td className="mono small">{p.tx ? `${p.tx.slice(0, 10)}…` : "–"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
