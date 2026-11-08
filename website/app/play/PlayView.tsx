"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import { AppFooter, AppHeader } from "@/components/AppChrome";
import { BinArt, ItemArt } from "@/components/GameArt";
import { BINS, LIVES } from "@/lib/game";
import { GameApiError, readLocalBest, saveNickname, saveScore, writeLocalBest, type SaveResult } from "@/lib/gameApi";
import { readSoundPref, writeSoundPref } from "@/lib/gameSound";
import GameBoard, { type FinishedGame } from "./GameBoard";
import Leaderboard from "./Leaderboard";
import "../dashboard/dashboard.css";
import "./play.css";

type Screen = "ready" | "playing" | "over";
type Save = { status: "idle" } | { status: "saving" } | { status: "saved"; res: SaveResult } | { status: "error"; message: string; tooFast: boolean };

/** "Sort It!", the sorting game for kids. `getToken` is null when nobody is signed in (local preview): you can play, not save. */
export default function PlayView({ getToken, nickname }: { getToken: (() => Promise<string>) | null; nickname: string | null }) {
  const [screen, setScreen] = useState<Screen>("ready");
  const [run, setRun] = useState(0);
  const [sound, setSound] = useState(readSoundPref);
  const [bestEver, setBestEver] = useState(readLocalBest);
  const [done, setDone] = useState<(FinishedGame & { beatLocal: boolean }) | null>(null);
  const [save, setSave] = useState<Save>({ status: "idle" });
  const [board, setBoard] = useState(0);              // bumped when the leaderboard should reload
  const [chosen, setChosen] = useState<string | null>(null);   // a nickname picked on this page; else the saved one
  const name = chosen ?? nickname;

  const submit = useCallback(async (g: FinishedGame) => {
    if (!getToken) { setSave({ status: "idle" }); return; }
    setSave({ status: "saving" });
    try {
      const token = await getToken();
      const res = await saveScore(token, { game_id: g.game_id, correct: g.correct, wrong: g.wrong, spilled: g.spilled, best_streak: g.best_streak, duration_ms: g.duration_ms });
      setSave({ status: "saved", res });
      if (res.best != null) { setBestEver((b) => Math.max(b, res.best!)); writeLocalBest(Math.max(readLocalBest(), res.best)); }
      setBoard((n) => n + 1);
    } catch (e) {
      setSave({ status: "error", message: (e as Error).message, tooFast: e instanceof GameApiError && e.status === 429 });
    }
  }, [getToken]);

  const onOver = useCallback((g: FinishedGame) => {
    const beatLocal = g.score > 0 && g.score > readLocalBest();
    setDone({ ...g, beatLocal });
    setScreen("over");
    if (beatLocal) { writeLocalBest(g.score); setBestEver((b) => Math.max(b, g.score)); }
    submit(g);
  }, [submit]);

  const start = () => { setDone(null); setSave({ status: "idle" }); setRun((n) => n + 1); setScreen("playing"); };
  const toggleSound = () => setSound((s) => { writeSoundPref(!s); return !s; });

  const newBest = save.status === "saved" ? save.res.personal_best : !!done?.beatLocal;   // the server knows your best across devices

  return (
    <div className="db">
      <AppHeader current="play" />
      <main className="db-wrap">
        <div className="db-inner">
          <div className="db-greet">
            <div>
              <h1>Sort It!</h1>
              <p>Swipe each item into the right bin before time runs out. {LIVES} hearts, so be careful!</p>
            </div>
          </div>

          <div className="play-grid">
            <div className="play-main">
              <div className="g-stage">
                <GameBoard key={run} active={screen !== "ready"} sound={sound} bestEver={bestEver} onOver={onOver} onQuit={() => { setRun((n) => n + 1); setScreen("ready"); }} />

                {screen === "ready" && (
                  <div className="g-overlay g-ready" role="dialog" aria-label="How to play">
                    <h2>Ready to sort?</h2>
                    <ol className="g-steps">
                      <li><span>1</span>Look at the item at the bottom.</li>
                      <li><span>2</span>Swipe it up into the right bin. You can also tap a bin.</li>
                      <li><span>3</span>Wrong bin or too slow? You lose a heart.</li>
                    </ol>
                    <ul className="g-legend" aria-label="What goes where">
                      {BINS.map((b) => (
                        <li key={b.id}><span className="g-legend-bin"><BinArt bin={b.id} open={false} /></span><b>{b.name}</b><small>{b.hint}</small></li>
                      ))}
                    </ul>
                    <button type="button" className="btn btn-primary g-play" onClick={start} autoFocus>Play</button>
                  </div>
                )}

                {screen === "over" && done && (
                  <div className="g-overlay g-over" role="dialog" aria-label="Game over">
                    <h2>{newBest && done.score > 0 ? "New best!" : done.correct >= 10 ? "Great sorting!" : "Nice try!"}</h2>
                    <p className="g-big"><b data-testid="final-score">{done.score}</b><span>points</span></p>
                    <dl className="g-result">
                      <div><dt>Sorted right</dt><dd>{done.correct}</dd></div>
                      <div><dt>Accuracy</dt><dd>{done.accuracy}%</dd></div>
                      <div><dt>Best streak</dt><dd>{done.best_streak}</dd></div>
                      <div><dt>Level</dt><dd>{done.level}</dd></div>
                    </dl>
                    <SaveLine save={save} signedIn={!!getToken} correct={done.correct} onRetry={() => submit(done)} />
                    <div className="g-actions">
                      <button type="button" className="btn btn-primary" onClick={start} autoFocus>Play again</button>
                      <Link href="/dashboard" className="btn btn-ghost">Back to dashboard</Link>
                    </div>
                  </div>
                )}
              </div>

              <div className="g-tools">
                <button type="button" className="g-tool" aria-pressed={sound} onClick={toggleSound}>
                  <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M4 9v6h4l5 4V5L8 9z" />{sound ? <path d="M16.5 8.5a5 5 0 010 7M19 6a8.5 8.5 0 010 12" /> : <path d="M17 9l5 6M22 9l-5 6" />}
                  </svg>
                  Sound {sound ? "on" : "off"}
                </button>
                <span className="g-keys">Tip: press <kbd>1</kbd> <kbd>2</kbd> <kbd>3</kbd> to pick a bin, <kbd>P</kbd> to pause.</span>
              </div>
            </div>

            <aside className="play-side">
              <Leaderboard getToken={getToken} refresh={board} />
              {getToken && <Nickname current={name} getToken={getToken} onSaved={(n) => { setChosen(n); setBoard((x) => x + 1); }} />}
              <section className="lb lb-about" aria-label="About the game">
                <h2>What is this?</h2>
                <p>
                  CashCan bins sort recycling into three openings, just like this game. Playing helps you learn what goes where, so
                  at the real bin you get it right and earn your cash back.
                </p>
                <div className="lb-items" aria-hidden="true">
                  <ItemArt id="can" /><ItemArt id="burger" /><ItemArt id="chip-bag" />
                </div>
              </section>
            </aside>
          </div>
          <AppFooter note="Sort It! · Scores are for fun · Nicknames only on the leaderboard" />
        </div>
      </main>
    </div>
  );
}

function SaveLine({ save, signedIn, correct, onRetry }: { save: Save; signedIn: boolean; correct: number; onRetry: () => void }) {
  if (!signedIn) return <p className="g-save">Log in to put your score on the leaderboard.</p>;
  if (correct === 0) return <p className="g-save">Sort at least one item to get on the leaderboard.</p>;
  if (save.status === "saving") return <p className="g-save" role="status">Saving your score…</p>;
  if (save.status === "saved") {
    const r = save.res;
    return <p className="g-save ok" role="status">Saved!{r.rank ? ` You're number ${r.rank} of all time.` : ""}{r.personal_best ? "" : r.best ? ` Your best is ${r.best}.` : ""}</p>;
  }
  if (save.status === "error") {
    return (
      <p className="g-save bad" role="alert">
        {save.message} {!save.tooFast && <button type="button" className="lb-retry" onClick={onRetry}>Try saving again</button>}
        {save.tooFast && <button type="button" className="lb-retry" onClick={onRetry}>Save now</button>}
      </p>
    );
  }
  return null;
}

/** The name shown on the leaderboard. Kids pick a nickname; the server only accepts simple, safe names. */
function Nickname({ current, getToken, onSaved }: { current: string | null; getToken: () => Promise<string>; onSaved: (n: string) => void }) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(current ?? "");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true); setErr(null);
    try { const r = await saveNickname(await getToken(), draft); onSaved(r.nickname); setDraft(r.nickname); setOpen(false); }
    catch (e) { setErr((e as Error).message); }
    setBusy(false);
  }

  return (
    <section className="lb lb-nick" aria-labelledby="nick-h">
      <h2 id="nick-h">Your leaderboard name</h2>
      {!open ? (
        <p>
          <b>{current ?? "A random Sorter name"}</b>{" "}
          <button type="button" className="lb-retry" onClick={() => { setDraft(current ?? ""); setOpen(true); }}>{current ? "Change" : "Pick a nickname"}</button>
        </p>
      ) : (
        <form onSubmit={(e) => { e.preventDefault(); save(); }}>
          <label htmlFor="nick" className="sr-only">Nickname</label>
          <input id="nick" value={draft} maxLength={16} autoComplete="off" spellCheck={false} onChange={(e) => setDraft(e.target.value)} aria-describedby="nick-help" />
          <p id="nick-help" className="lb-help">2 to 16 letters or numbers. Please don&apos;t use your real full name.</p>
          {err && <p className="g-save bad" role="alert">{err}</p>}
          <div className="g-actions">
            <button type="submit" className="btn btn-primary" disabled={busy || draft.trim().length < 2}>{busy ? "Saving…" : "Save name"}</button>
            <button type="button" className="btn btn-ghost" onClick={() => setOpen(false)}>Cancel</button>
          </div>
        </form>
      )}
    </section>
  );
}
