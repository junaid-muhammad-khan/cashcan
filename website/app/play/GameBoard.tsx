"use client";

import { useEffect, useRef, useState } from "react";
import gsap from "gsap";
import { BinArt, Heart, ItemArt } from "@/components/GameArt";
import {
  BINS, CHEERS, LIVES, STREAK_CHEER_EVERY, accuracyOf, lessonFor, levelOf, newGameId, nextItem, scoreOf, timeForLevel,
  type ArtId, type BinId, type GameResult, type Item,
} from "@/lib/game";
import { play } from "@/lib/gameSound";

// One game of Sort It!: items wait along the bottom, the front one has a timer. Swipe (or tap a bin, or press 1 2 3) to sort it.
// Wrong bin or too slow = a heart gone; three hearts gone = game over. Everything that changes every frame lives in refs
// and the DOM; React state only holds what the screen shows (hearts, score, queue, message).

type Q = { uid: number; item: Item };
type Msg = { text: string; tone: "good" | "bad" | "info"; n: number };
interface View { lives: number; correct: number; wrong: number; spilled: number; streak: number; best: number; queue: Q[]; msg: Msg | null; paused: boolean; over: boolean }

interface G {
  id: string; lives: number; correct: number; wrong: number; spilled: number; streak: number; best: number; uid: number; msgN: number;
  queue: Q[]; recent: ArtId[]; locked: boolean; over: boolean; paused: boolean; remaining: number; limit: number; playMs: number;
}

const QUEUE_SHOWN = 5;
const RESOLVE_MS = 700;           // every item takes at least this long to resolve, which also keeps scores honest
const CIRC = 2 * Math.PI * 46;    // timer ring length

const newG = (): G => ({ id: newGameId(), lives: LIVES, correct: 0, wrong: 0, spilled: 0, streak: 0, best: 0, uid: 0, msgN: 0,
  queue: [], recent: [], locked: false, over: false, paused: false, remaining: 0, limit: 0, playMs: 0 });

const emptyView = (): View => ({ lives: LIVES, correct: 0, wrong: 0, spilled: 0, streak: 0, best: 0, queue: [], msg: null, paused: false, over: false });

export interface FinishedGame extends GameResult { score: number; level: number; accuracy: number }

interface Props {
  active: boolean;               // false = just show the board (the "ready" screen); true = play
  sound: boolean;
  bestEver: number;              // the player's best score so far, shown as "Best"
  onOver: (r: FinishedGame) => void;
  onQuit: () => void;
}

export default function GameBoard({ active, sound, bestEver, onOver, onQuit }: Props) {
  const [view, setView] = useState<View>(emptyView);
  const [hover, setHover] = useState<BinId | null>(null);
  const [fx, setFx] = useState<{ bin: BinId; kind: "ok" | "bad"; n: number } | null>(null);
  const boardRef = useRef<HTMLDivElement>(null);
  const binRefs = useRef<Record<BinId, HTMLButtonElement | null>>({ cans: null, organics: null, waste: null });
  const gRef = useRef<G>(newG());
  const propsRef = useRef({ sound, onOver });
  propsRef.current = { sound, onOver };
  const reduced = useRef(false);
  const timers = useRef<number[]>([]);
  const hoverRef = useRef<BinId | null>(null);

  const later = (fn: () => void, ms: number) => { timers.current.push(window.setTimeout(fn, ms)); };
  const sfx = (k: Parameters<typeof play>[0]) => { if (propsRef.current.sound) play(k); };
  const frontDrag = () => boardRef.current?.querySelector<HTMLElement>(".g-slot.s0 .g-drag") ?? null;

  const refresh = () => {
    const g = gRef.current;
    setView((v) => ({ ...v, lives: g.lives, correct: g.correct, wrong: g.wrong, spilled: g.spilled, streak: g.streak, best: g.best,
      queue: g.queue.slice(0, QUEUE_SHOWN), paused: g.paused, over: g.over }));
  };
  const say = (text: string, tone: Msg["tone"], ms = 1900) => {
    const g = gRef.current, n = ++g.msgN;
    setView((v) => ({ ...v, msg: { text, tone, n } }));
    later(() => setView((v) => (v.msg?.n === n ? { ...v, msg: null } : v)), ms);
  };
  const fill = () => {
    const g = gRef.current;
    while (g.queue.length < QUEUE_SHOWN) {
      const item = nextItem(levelOf(g.correct), g.recent);
      g.recent.push(item.id);
      g.queue.push({ uid: ++g.uid, item });
    }
  };
  const startTimer = () => { const g = gRef.current; g.limit = timeForLevel(levelOf(g.correct)); g.remaining = g.limit; };

  const centerOf = (el: Element) => { const r = el.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; };
  const nearestBin = (x: number): BinId => {
    let best: BinId = "cans", d = Infinity;
    for (const b of BINS) { const el = binRefs.current[b.id]; if (!el) continue; const dd = Math.abs(centerOf(el).x - x); if (dd < d) { d = dd; best = b.id; } }
    return best;
  };

  const finish = () => {
    const g = gRef.current;
    if (g.over) return;
    g.over = true;
    refresh();
    sfx("over");
    const accuracy = accuracyOf(g.correct, g.wrong, g.spilled);
    propsRef.current.onOver({ game_id: g.id, correct: g.correct, wrong: g.wrong, spilled: g.spilled, best_streak: g.best,
      duration_ms: Math.round(g.playMs), score: scoreOf(g.correct, g.best), level: levelOf(g.correct), accuracy });
  };

  const resolve = (choice: BinId | "spill") => {
    const g = gRef.current;
    if (!active || g.locked || g.over || g.paused || !g.queue[0]) return;
    g.locked = true;
    const item = g.queue[0].item;
    const drag = frontDrag();
    const bin = choice === "spill" ? null : binRefs.current[choice];
    const fly = (extra?: gsap.core.Timeline) => {
      if (!drag || !bin || reduced.current) { if (drag) gsap.set(drag, { autoAlpha: 0 }); return; }
      const a = centerOf(drag), b = centerOf(bin);
      const tl = gsap.timeline();
      tl.to(drag, { x: `+=${b.x - a.x}`, y: `+=${b.y - a.y}`, scale: 0.4, rotation: 0, duration: 0.3, ease: "power2.in" });
      if (extra) tl.add(extra);
      else tl.to(drag, { autoAlpha: 0, duration: 0.1 });
    };

    if (choice === item.bin) {
      g.correct += 1; g.streak += 1; g.best = Math.max(g.best, g.streak);
      const leveled = levelOf(g.correct) > levelOf(g.correct - 1);
      fly();
      setFx({ bin: choice, kind: "ok", n: g.msgN + 1 });
      if (leveled) { sfx("cheer"); say(`Level ${levelOf(g.correct)}! Items come faster.`, "info"); }
      else if (g.streak % STREAK_CHEER_EVERY === 0) { sfx("cheer"); say(`${g.streak} in a row! Keep going!`, "good"); }
      else { sfx("good"); say(CHEERS[g.correct % CHEERS.length], "good", 1200); }
    } else {
      const spill = choice === "spill";
      g.lives -= 1; g.streak = 0;
      if (spill) g.spilled += 1; else g.wrong += 1;
      if (spill) {
        if (drag) { if (reduced.current) gsap.set(drag, { autoAlpha: 0 }); else gsap.to(drag, { y: "+=150", rotation: 28, autoAlpha: 0, duration: 0.5, ease: "power2.in" }); }
        sfx("spill");
      } else {
        const back = reduced.current || !drag ? undefined : gsap.timeline().to(drag, { y: "+=90", scale: 0.8, autoAlpha: 0, duration: 0.35, ease: "power2.out" });
        fly(back);
        setFx({ bin: choice as BinId, kind: "bad", n: g.msgN + 1 });
        sfx("bad");
      }
      say(lessonFor(item, spill ? "spill" : "wrong"), "bad", 2600);
    }
    boardRef.current?.querySelector(".g-slot.s0")?.classList.add("done");   // hide its timer ring and label while it resolves
    refresh();
    later(() => {
      g.queue.shift();
      fill();
      if (g.lives <= 0) { finish(); return; }
      startTimer();
      g.locked = false;
      refresh();
    }, RESOLVE_MS);
  };

  const setPaused = (p: boolean) => {
    const g = gRef.current;
    if (g.over || !active) return;
    g.paused = p;
    refresh();
  };

  // ---- start a game, run the timer
  useEffect(() => {
    reduced.current = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    gRef.current = newG();
    fill();
    if (!active) { refresh(); return; }
    startTimer();
    refresh();
    let raf = 0, last = performance.now();
    const tick = (now: number) => {
      const dt = Math.min(now - last, 100);   // a long gap (tab switch, slow frame) never costs a heart
      last = now;
      const g = gRef.current;
      if (!g.over && !g.paused) {
        g.playMs += dt;
        if (!g.locked) {
          g.remaining -= dt;
          const f = Math.max(0, g.remaining / g.limit);
          const ring = boardRef.current?.querySelector<SVGCircleElement>(".g-slot.s0 .g-ring-fg");
          if (ring) { ring.style.strokeDashoffset = String(CIRC * (1 - f)); ring.style.stroke = f > 0.5 ? "#2BB673" : f > 0.25 ? "#E3B23C" : "#E5484D"; }
          if (g.remaining <= 0) resolve("spill");
        }
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    const onHidden = () => { if (document.hidden) setPaused(true); };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" || e.key.toLowerCase() === "p") { setPaused(!gRef.current.paused); return; }
      const i = ["1", "2", "3"].indexOf(e.key);
      if (i >= 0) resolve(BINS[i].id);
    };
    document.addEventListener("visibilitychange", onHidden);
    window.addEventListener("keydown", onKey);
    return () => {
      cancelAnimationFrame(raf);
      document.removeEventListener("visibilitychange", onHidden);
      window.removeEventListener("keydown", onKey);
      timers.current.forEach(clearTimeout); timers.current = [];
      gsap.killTweensOf(".g-drag");
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);

  // ---- swipe
  const drag = useRef<{ id: number; sx: number; sy: number; lastY: number; lastT: number; vy: number } | null>(null);
  const laneAt = (dy: number): BinId | null => {
    const el = frontDrag();
    return el && dy < -30 ? nearestBin(centerOf(el).x) : null;
  };
  const onDown = (e: React.PointerEvent<HTMLDivElement>) => {
    const g = gRef.current;
    if (!active || g.locked || g.over || g.paused) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    drag.current = { id: e.pointerId, sx: e.clientX, sy: e.clientY, lastY: e.clientY, lastT: e.timeStamp, vy: 0 };
  };
  const onMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const d = drag.current;
    if (!d || d.id !== e.pointerId) return;
    const dx = e.clientX - d.sx, dy = e.clientY - d.sy;
    d.vy = (e.clientY - d.lastY) / Math.max(1, e.timeStamp - d.lastT); d.lastY = e.clientY; d.lastT = e.timeStamp;
    gsap.set(e.currentTarget, { x: dx, y: dy, rotation: dx * 0.05 });
    const lane = laneAt(dy);
    if (lane !== hoverRef.current) { hoverRef.current = lane; setHover(lane); }
  };
  const onUp = (e: React.PointerEvent<HTMLDivElement>) => {
    const d = drag.current;
    if (!d || d.id !== e.pointerId) return;
    drag.current = null;
    hoverRef.current = null; setHover(null);
    if (gRef.current.locked) return;
    const dy = e.clientY - d.sy;
    if (dy < -70 || (dy < -35 && d.vy < -0.5)) { const lane = laneAt(dy) ?? nearestBin(centerOf(e.currentTarget).x); resolve(lane); }
    else gsap.to(e.currentTarget, { x: 0, y: 0, rotation: 0, duration: 0.25, ease: "back.out(2)" });
  };

  const score = scoreOf(view.correct, view.best);
  const acc = accuracyOf(view.correct, view.wrong, view.spilled);
  const front = view.queue[0];

  return (
    <div className="g-board" ref={boardRef} data-state={view.over ? "over" : view.paused ? "paused" : active ? "playing" : "ready"}>
      <div className="g-hud">
        <dl className="g-stats">
          <div><dt>Best</dt><dd data-testid="best">{Math.max(bestEver, score)}</dd></div>
          <div><dt>Accuracy</dt><dd data-testid="accuracy">{view.correct + view.wrong + view.spilled ? `${acc}%` : "-"}</dd></div>
          <div><dt>Streak</dt><dd data-testid="streak">{view.streak}</dd></div>
        </dl>
        <div className="g-score"><span>Score</span><b data-testid="score">{score}</b><small>Level {levelOf(view.correct)}</small></div>
        <div className="g-lives" role="img" aria-label={`${view.lives} of ${LIVES} lives left`} data-lives={view.lives}>
          {Array.from({ length: LIVES }, (_, i) => <Heart key={i} lost={i >= view.lives} />)}
        </div>
      </div>

      <div className="g-bins" role="group" aria-label="Bins. Choose where the item goes.">
        {BINS.map((b, i) => (
          <button key={b.id} type="button" ref={(el) => { binRefs.current[b.id] = el; }} disabled={!active || view.over}
            className={`g-bin${hover === b.id ? " hover" : ""}${fx?.bin === b.id ? ` fx-${fx.kind}` : ""}`} data-bin={b.id}
            style={{ ["--bin" as string]: b.color }} onClick={() => resolve(b.id)} onAnimationEnd={() => setFx(null)}
            aria-label={`${b.name}. Press ${i + 1} or tap to put the item here.`}>
            <BinArt bin={b.id} open={hover === b.id} />
            <span className="g-bin-name">{b.name}</span>
            <kbd aria-hidden="true">{i + 1}</kbd>
          </button>
        ))}
      </div>

      <div className={`g-msg ${view.msg?.tone ?? ""}`} role="status" aria-live="polite" data-testid="msg">{view.msg?.text ?? ""}</div>

      <div className="g-queue" aria-label="Items waiting to be sorted">
        {view.queue.map((q, i) => (
          <div key={q.uid} className={`g-slot s${i}`}>
            {i === 0 && active && (
              <svg className="g-ring" viewBox="0 0 100 100" aria-hidden="true">
                <circle cx="50" cy="50" r="46" className="g-ring-bg" />
                <circle cx="50" cy="50" r="46" className="g-ring-fg" strokeDasharray={CIRC} strokeDashoffset={0} transform="rotate(-90 50 50)" />
              </svg>
            )}
            <div className="g-drag" role={i === 0 ? "img" : undefined} aria-label={i === 0 ? q.item.name : undefined} aria-hidden={i === 0 ? undefined : true}
              data-item={q.item.id} onPointerDown={i === 0 ? onDown : undefined} onPointerMove={i === 0 ? onMove : undefined}
              onPointerUp={i === 0 ? onUp : undefined} onPointerCancel={i === 0 ? onUp : undefined}>
              <ItemArt id={q.item.id} />
            </div>
            {i === 0 && <span className="g-name" data-testid="item-name">{q.item.name}</span>}
          </div>
        ))}
      </div>

      {active && front && view.correct === 0 && !view.over && (
        <p className="g-hint"><span aria-hidden="true" className="g-hint-arrow">↑</span> Swipe it up into the right bin</p>
      )}

      {active && !view.over && (
        <button type="button" className="g-pause" onClick={() => setPaused(true)} aria-label="Pause the game">
          <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M8 5v14M16 5v14" stroke="currentColor" strokeWidth="3" strokeLinecap="round" /></svg>
        </button>
      )}

      {view.paused && (
        <div className="g-overlay" role="dialog" aria-label="Game paused">
          <h2>Paused</h2>
          <p>Take a breath. Your hearts are safe.</p>
          <div className="g-actions">
            <button type="button" className="btn btn-primary" onClick={() => setPaused(false)} autoFocus>Keep playing</button>
            <button type="button" className="btn btn-ghost" onClick={onQuit}>Stop game</button>
          </div>
        </div>
      )}
    </div>
  );
}
