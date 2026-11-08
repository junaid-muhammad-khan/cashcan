// Errors from the face API. Its `detail` is either a plain string or an object { message, code, ... }.
// code "database_unavailable" (HTTP 503) means the database is paused or unreachable, e.g. its free daily limit is used up.
export const DB_PAUSED = "database_unavailable";

export const isDbPaused = (e: unknown): boolean => (e as { code?: string } | null)?.code === DB_PAUSED;

export function parseDetail(body: unknown, fallback: string): { message: string; code?: string } {
  const d = (body as { detail?: unknown } | null)?.detail;
  if (typeof d === "string") return { message: d };
  if (d && typeof d === "object") {
    const o = d as { message?: unknown; code?: unknown };
    return { message: typeof o.message === "string" ? o.message : fallback, code: typeof o.code === "string" ? o.code : undefined };
  }
  return { message: fallback };
}
