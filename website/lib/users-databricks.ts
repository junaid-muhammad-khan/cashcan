import { randomUUID } from "node:crypto";
import type { UserRecord } from "./users-file";

// Website accounts in Databricks (table workspace.cashcan_web.users, created by databricks/website_users.sql).
// Talks to the SQL Statement API over HTTPS with bound parameters only, so it works on serverless hosts like Vercel.
const COLS = "id, name, email, password_hash, wallet_address, face_opt_in, created_at, reset_token_hash, reset_expires";
const TABLE = () => process.env.DATABRICKS_USERS_TABLE || "workspace.cashcan_web.users";

type Param = string | boolean | number | null;

async function sql(statement: string, params: Record<string, Param> = {}): Promise<string[][]> {
  const host = (process.env.DATABRICKS_HOST || "").replace(/\/$/, "");
  const res = await fetch(`${host.startsWith("http") ? host : "https://" + host}/api/2.0/sql/statements`, {
    method: "POST",
    headers: { Authorization: `Bearer ${process.env.DATABRICKS_TOKEN}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      warehouse_id: process.env.DATABRICKS_WAREHOUSE_ID,
      statement,
      wait_timeout: "50s",
      on_wait_timeout: "CANCEL",
      parameters: Object.entries(params).map(([name, v]) =>
        v === null ? { name } : { name, value: String(v), type: typeof v === "boolean" ? "BOOLEAN" : typeof v === "number" ? "BIGINT" : "STRING" },
      ),
    }),
    cache: "no-store",
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok || body?.status?.state !== "SUCCEEDED") {
    throw new Error(`Databricks SQL failed: ${body?.status?.error?.message || body?.message || res.status}`);
  }
  return body?.result?.data_array ?? [];
}

function toUser(r: string[]): UserRecord {
  return {
    id: r[0], name: r[1], email: r[2], passwordHash: r[3], walletAddress: r[4] ?? null,
    faceOptIn: r[5] === "true", createdAt: r[6],
    resetTokenHash: r[7] ?? null, resetExpires: r[8] == null ? null : Number(r[8]),
  };
}

export const findUserByEmail = async (email: string) =>
  (await sql(`SELECT ${COLS} FROM ${TABLE()} WHERE email = :e LIMIT 1`, { e: email.trim().toLowerCase() })).map(toUser)[0];

export const findUserById = async (id: string) =>
  (await sql(`SELECT ${COLS} FROM ${TABLE()} WHERE id = :i LIMIT 1`, { i: id })).map(toUser)[0];

export const findUserByResetHash = async (hash: string) =>
  (await sql(`SELECT ${COLS} FROM ${TABLE()} WHERE reset_token_hash = :h AND reset_expires > :now LIMIT 1`, { h: hash, now: Date.now() })).map(toUser)[0];

export class EmailTakenError extends Error {}

export async function createUser(input: Omit<UserRecord, "id" | "createdAt">): Promise<UserRecord> {
  const email = input.email.trim().toLowerCase();
  const id = randomUUID();
  // One statement: insert only if no row has this email (Delta has no UNIQUE constraint).
  const out = await sql(
    `INSERT INTO ${TABLE()} (id, name, email, password_hash, wallet_address, face_opt_in, created_at)
     SELECT :id, :name, :email, :pw, :wallet, :face, current_timestamp()
     WHERE NOT EXISTS (SELECT 1 FROM ${TABLE()} WHERE email = :email)`,
    { id, name: input.name, email, pw: input.passwordHash, wallet: input.walletAddress, face: input.faceOptIn },
  );
  if (Number(out[0]?.[0] ?? 0) === 0) throw new EmailTakenError();
  return (await findUserById(id))!;
}

const FIELD: Record<string, string> = {
  name: "name", passwordHash: "password_hash", walletAddress: "wallet_address",
  faceOptIn: "face_opt_in", resetTokenHash: "reset_token_hash", resetExpires: "reset_expires",
};

export async function updateUser(id: string, patch: Partial<Omit<UserRecord, "id" | "email" | "createdAt">>) {
  const entries = Object.entries(patch).filter(([k, v]) => k in FIELD && v !== undefined);
  if (entries.length) {
    const set = entries.map(([k], i) => `${FIELD[k]} = :p${i}`).join(", ");
    const params: Record<string, Param> = { id };
    entries.forEach(([, v], i) => (params[`p${i}`] = v as Param));
    await sql(`UPDATE ${TABLE()} SET ${set} WHERE id = :id`, params);
  }
  return findUserById(id);
}
