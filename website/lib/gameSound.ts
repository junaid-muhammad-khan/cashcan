// Tiny sound effects made with the browser's audio engine (no files). Only plays after a tap, and can be muted.
export type Sfx = "good" | "bad" | "spill" | "cheer" | "over";

let ctx: AudioContext | null = null;
const SOUND_KEY = "cashcan.game.sound";

export const readSoundPref = (): boolean => { try { return localStorage.getItem(SOUND_KEY) !== "off"; } catch { return true; } };
export const writeSoundPref = (on: boolean) => { try { localStorage.setItem(SOUND_KEY, on ? "on" : "off"); } catch { /* private mode */ } };

function tone(c: AudioContext, freq: number, start: number, dur: number, type: OscillatorType = "sine", vol = 0.12) {
  const o = c.createOscillator(), g = c.createGain();
  o.type = type; o.frequency.setValueAtTime(freq, c.currentTime + start);
  g.gain.setValueAtTime(0.0001, c.currentTime + start);
  g.gain.exponentialRampToValueAtTime(vol, c.currentTime + start + 0.02);
  g.gain.exponentialRampToValueAtTime(0.0001, c.currentTime + start + dur);
  o.connect(g).connect(c.destination);
  o.start(c.currentTime + start); o.stop(c.currentTime + start + dur + 0.05);
}

export function play(kind: Sfx) {
  try {
    ctx = ctx ?? new AudioContext();
    if (ctx.state === "suspended") void ctx.resume();
    if (kind === "good") { tone(ctx, 660, 0, 0.12); tone(ctx, 880, 0.08, 0.16); }
    else if (kind === "cheer") { [523, 659, 784, 1047].forEach((f, i) => tone(ctx!, f, i * 0.07, 0.16)); }
    else if (kind === "bad") { tone(ctx, 220, 0, 0.22, "triangle", 0.14); tone(ctx, 165, 0.12, 0.26, "triangle", 0.14); }
    else if (kind === "spill") { tone(ctx, 300, 0, 0.3, "sawtooth", 0.06); tone(ctx, 180, 0.16, 0.3, "triangle", 0.1); }
    else { [440, 392, 330, 262].forEach((f, i) => tone(ctx!, f, i * 0.14, 0.24, "triangle", 0.12)); }
  } catch { /* no audio available: the game works without it */ }
}
