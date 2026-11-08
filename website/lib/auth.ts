import { createHash, createHmac, randomBytes, scrypt as scryptCb, timingSafeEqual } from "node:crypto";
import { promisify } from "node:util";
import { cookies } from "next/headers";
import { findUserById, type UserRecord } from "./users";

const scrypt = promisify(scryptCb) as (pw: string, salt: Buffer, len: number) => Promise<Buffer>;

export const SESSION_COOKIE = "cashcan_session";
const SESSION_DAYS = 7;

function secret(): string {
  const s = process.env.AUTH_SECRET;
  if (s && s.length >= 32) return s;
  if (process.env.NODE_ENV === "production") {
    throw new Error("AUTH_SECRET must be set (32+ chars) in production");
  }
  return "dev-only-insecure-secret-change-me-0000000000";
}

export async function hashPassword(password: string): Promise<string> {
  const salt = randomBytes(16);
  const key = await scrypt(password, salt, 64);
  return `scrypt$${salt.toString("hex")}$${key.toString("hex")}`;
}

export async function verifyPassword(password: string, stored: string): Promise<boolean> {
  const [algo, saltHex, keyHex] = stored.split("$");
  if (algo !== "scrypt" || !saltHex || !keyHex) return false;
  const expected = Buffer.from(keyHex, "hex");
  const key = await scrypt(password, Buffer.from(saltHex, "hex"), expected.length);
  return timingSafeEqual(key, expected);
}

function sign(payload: string): string {
  return createHmac("sha256", secret()).update(payload).digest("base64url");
}

// remember = true: 7-day persistent cookie. false: browser-session cookie whose token
// still expires server-side after 12 hours.
export function createSessionToken(userId: string, remember = true): { token: string; expires: Date; remember: boolean } {
  const ms = remember ? SESSION_DAYS * 86_400_000 : 12 * 3_600_000;
  const expires = new Date(Date.now() + ms);
  const payload = Buffer.from(JSON.stringify({ uid: userId, exp: expires.getTime() })).toString("base64url");
  return { token: `${payload}.${sign(payload)}`, expires, remember };
}

export function readSessionToken(token: string | undefined): string | null {
  if (!token) return null;
  const [payload, sig] = token.split(".");
  if (!payload || !sig) return null;
  const expected = Buffer.from(sign(payload));
  const given = Buffer.from(sig);
  if (expected.length !== given.length || !timingSafeEqual(expected, given)) return null;
  try {
    const { uid, exp } = JSON.parse(Buffer.from(payload, "base64url").toString());
    return typeof uid === "string" && typeof exp === "number" && exp > Date.now() ? uid : null;
  } catch {
    return null;
  }
}

export const sessionCookieOptions = (expires: Date, remember = true) => ({
  httpOnly: true,
  sameSite: "lax" as const,
  secure: process.env.NODE_ENV === "production",
  path: "/",
  ...(remember ? { expires } : {}),
});

export function hashResetToken(token: string): string {
  return createHash("sha256").update(token).digest("hex");
}

export function newResetToken(): string {
  return randomBytes(32).toString("base64url");
}

export async function getCurrentUser(): Promise<UserRecord | null> {
  const jar = await cookies();
  const uid = readSessionToken(jar.get(SESSION_COOKIE)?.value);
  return uid ? (await findUserById(uid)) ?? null : null;
}

export function publicUser(u: UserRecord) {
  return { id: u.id, name: u.name, email: u.email, walletAddress: u.walletAddress, faceOptIn: u.faceOptIn };
}
