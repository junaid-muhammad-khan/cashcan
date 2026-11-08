// Calls for the sorting game's leaderboard (face_api /game/*). Reading the board needs no login; saving does.
import { parseDetail } from "./errors";
import { FACE_API } from "./faceApi";

export type Period = "week" | "all";

export interface LeaderRow {
  rank: number;
  name: string;
  score: number;
  correct: number;
  best_streak: number;
  level: number;
  accuracy: number;
  is_me: boolean;
}

export interface Board {
  period: Period;
  leaderboard: LeaderRow[];
  me: { best: number | null; rank: number | null } | null;
}

export interface SaveResult {
  saved: boolean;
  score: number;
  best: number | null;
  personal_best: boolean;
  rank: number | null;
}

export class GameApiError extends Error {
  constructor(message: string, public status: number, public code?: string) { super(message); }
}

async function call<T>(path: string, init: RequestInit, token?: string): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body) headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let res: Response;
  try {
    res = await fetch(`${FACE_API}${path}`, { ...init, headers });
  } catch {
    throw new GameApiError("We couldn't reach the leaderboard. Check your connection.", 0);
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) { const d = parseDetail(body, `Something went wrong (${res.status}).`); throw new GameApiError(d.message, res.status, d.code); }
  return body as T;
}

export const getBoard = (period: Period, token?: string) =>
  call<Board>(`/game/leaderboard?period=${period}&limit=10`, { method: "GET", cache: "no-store" }, token);

export const saveScore = (token: string, result: object) =>
  call<SaveResult>("/game/scores", { method: "POST", body: JSON.stringify(result) }, token);

export const saveNickname = (token: string, nickname: string) =>
  call<{ nickname: string }>("/game/nickname", { method: "PUT", body: JSON.stringify({ nickname }) }, token);

const BEST_KEY = "cashcan.game.best";
export const readLocalBest = (): number => { try { return Number(localStorage.getItem(BEST_KEY)) || 0; } catch { return 0; } };
export const writeLocalBest = (n: number) => { try { localStorage.setItem(BEST_KEY, String(n)); } catch { /* private mode */ } };
