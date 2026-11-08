"use client";

import { useEffect, useState } from "react";
import { isDbPaused } from "@/lib/errors";
import { getBoard, type Board, type Period } from "@/lib/gameApi";

type Load = { status: "loading" } | { status: "error"; message: string; paused: boolean } | { status: "ready"; board: Board };

/** Top ten players for the week or all time. Nicknames only. `refresh` changes when a new score has been saved. */
export default function Leaderboard({ getToken, refresh }: { getToken: (() => Promise<string>) | null; refresh: number }) {
  const [period, setPeriod] = useState<Period>("week");
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let alive = true;
    setLoad((l) => (l.status === "ready" ? l : { status: "loading" }));   // keep showing the old board while it updates
    (async () => {
      try {
        let token: string | undefined;
        try { token = getToken ? await getToken() : undefined; } catch { token = undefined; }   // signed-out reading still works
        const board = await getBoard(period, token);
        if (alive) setLoad({ status: "ready", board });
      } catch (e) {
        if (alive) setLoad({ status: "error", message: (e as Error).message, paused: isDbPaused(e) });
      }
    })();
    return () => { alive = false; };
  }, [period, refresh, nonce, getToken]);

  return (
    <section className="lb" aria-labelledby="lb-h">
      <div className="lb-head">
        <h2 id="lb-h">Leaderboard</h2>
        <div className="lb-tabs" role="group" aria-label="Time period">
          {(["week", "all"] as const).map((p) => (
            <button key={p} type="button" aria-pressed={period === p} className={period === p ? "on" : undefined} onClick={() => setPeriod(p)}>
              {p === "week" ? "This week" : "All time"}
            </button>
          ))}
        </div>
      </div>

      {load.status === "loading" && <p className="lb-note">Loading the best sorters…</p>}
      {load.status === "error" && (
        <div className="lb-note" role="alert">
          {load.message}{load.paused ? " You can still play, and your score will save when it's back." : ""} <button type="button" className="lb-retry" onClick={() => setNonce((n) => n + 1)}>Try again</button>
        </div>
      )}
      {load.status === "ready" && load.board.leaderboard.length === 0 && (
        <p className="lb-note">No scores {period === "week" ? "this week" : "yet"}. Be the first on the board!</p>
      )}
      {load.status === "ready" && load.board.leaderboard.length > 0 && (
        <ol className="lb-list">
          {load.board.leaderboard.map((r) => (
            <li key={r.rank} className={r.is_me ? "me" : undefined}>
              <span className="lb-rank" aria-label={`Rank ${r.rank}`}>{r.rank}</span>
              <span className="lb-name"><span className="lb-who">{r.name}{r.is_me && <em> (you)</em>}</span><small>Level {r.level} · {r.accuracy}% right</small></span>
              <span className="lb-score">{r.score}</span>
            </li>
          ))}
        </ol>
      )}
      {load.status === "ready" && load.board.me?.best != null && (
        <p className="lb-me">Your best {period === "week" ? "this week" : "ever"}: <b>{load.board.me.best}</b>{load.board.me.rank ? ` · rank ${load.board.me.rank}` : ""}</p>
      )}
    </section>
  );
}
