// Thin client for the CashCan face API (../face_api). In production Vercel routes
// /face-api/* to that service (see ../vercel.json). For local dev, run the API on :8000
// and set FACE_API_ORIGIN=http://localhost:8000 so next.config.mjs proxies /face-api/*.
export const FACE_API = (process.env.NEXT_PUBLIC_FACE_API_URL || "/face-api").replace(/\/$/, "");

// Auth0 "sub" (e.g. "google-oauth2|1234") isn't a valid face-API user_id, so make a safe one.
// Only used when the API runs without Auth0 (local dev); with Auth0 the API takes identity from the token.
export function userIdFromSub(sub: string): string {
  return sub.replace(/[^A-Za-z0-9_.-]/g, "_").slice(0, 64);
}

export interface Me {
  user_id: string;
  sol_wallet: string | null;
  face_enrolled: boolean;
  pseudonym?: string | null;   // the public nickname (game leaderboard)
}

export class FaceApiError extends Error {
  constructor(message: string, public status: number, public problems: string[] = [], public code?: string) {
    super(message);
  }
}

async function call<T>(path: string, init: RequestInit, token?: string): Promise<T> {
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let res: Response;
  try {
    res = await fetch(`${FACE_API}${path}`, { ...init, headers });
  } catch {
    throw new FaceApiError("We couldn't reach the face service. Check your connection and try again.", 0);
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const d = body?.detail;
    const message = typeof d === "string" ? d : d?.message ?? `The face service returned an error (${res.status}).`;
    throw new FaceApiError(message, res.status, Array.isArray(d?.problems) ? d.problems : [], typeof d?.code === "string" ? d.code : undefined);
  }
  return body as T;
}

export const getMe = (token: string) => call<Me>("/me", { method: "GET" }, token);

/** What saving a wallet did to rewards held for lack of one (they are paid right away; the rest by the retry job). */
export interface HeldRelease { held_queued?: number; held_paid?: number; held_error?: string }

export const saveWallet = (token: string, wallet: string) =>
  call<Me & HeldRelease>("/me", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ sol_wallet: wallet }) }, token);

export interface PoseResult { found: boolean; pose?: "front" | "left" | "right" | "between" | "profile"; turn?: number; hint?: string }

/** Which way is the head turned in this frame? Nothing is stored. */
export function checkPose(frame: Blob) {
  const fd = new FormData();
  fd.append("frame", frame, "frame.jpg");
  return call<PoseResult>("/pose", { method: "POST", body: fd });
}

export function enroll(frames: Blob[], opts: { token?: string; userId: string; wallet: string; poses?: string[]; replace?: boolean }) {
  const fd = new FormData();
  fd.set("consent", "true");
  fd.set("user_id", opts.userId); // ignored by the API when Auth0 is on
  fd.set("wallet", opts.wallet);
  if (opts.replace) fd.set("replace", "true"); // delete the old account that holds this same face and use this one
  if (opts.poses) fd.set("poses", opts.poses.join(",")); // the API checks each photo really shows its direction
  frames.forEach((f, i) => fd.append("frames", f, `frame${i + 1}.jpg`));
  return call<{ enrolled: boolean; frames_used: number; problems: string[] }>("/enroll", { method: "POST", body: fd }, opts.token);
}

export interface MatchResult {
  matched: boolean;
  user_id?: string;
  score?: number;
  reason?: string;
  message?: string;
}

export function matchFrame(frame: Blob) {
  const fd = new FormData();
  fd.append("frame", frame, "frame.jpg");
  return call<MatchResult>("/match", { method: "POST", body: fd });
}
