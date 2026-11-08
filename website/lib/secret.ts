import { timingSafeEqual } from "node:crypto";

/** Constant-time check of an "Authorization: Bearer <secret>" header. False when the secret is not configured. */
export function bearerMatches(header: string | null, secret: string | undefined): boolean {
  if (!secret || !header) return false;
  const a = Buffer.from(header), b = Buffer.from(`Bearer ${secret}`);
  return a.length === b.length && timingSafeEqual(a, b);
}
