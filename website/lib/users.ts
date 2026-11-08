import { promises as fs } from "node:fs";
import path from "node:path";
import { randomUUID } from "node:crypto";

// Prototype user store: a JSON file under .data/ (gitignored). Good enough for a
// single-instance hackathon deploy; swap for a real database before production.
export interface UserRecord {
  id: string;
  name: string;
  email: string;
  passwordHash: string;
  walletAddress: string | null;
  faceOptIn: boolean;
  createdAt: string;
  // Password reset: only the SHA-256 of the token is stored, never the token itself.
  resetTokenHash?: string | null;
  resetExpires?: number | null;
}

const DATA_DIR = path.join(process.cwd(), ".data");
const FILE = path.join(DATA_DIR, "users.json");

let writeQueue: Promise<unknown> = Promise.resolve();

async function readAll(): Promise<UserRecord[]> {
  try {
    return JSON.parse(await fs.readFile(FILE, "utf8")) as UserRecord[];
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") return [];
    throw err;
  }
}

async function writeAll(users: UserRecord[]): Promise<void> {
  await fs.mkdir(DATA_DIR, { recursive: true });
  const tmp = `${FILE}.${process.pid}.tmp`;
  await fs.writeFile(tmp, JSON.stringify(users, null, 2), { mode: 0o600 });
  await fs.rename(tmp, FILE);
}

// Serialize read-modify-write cycles so concurrent requests can't clobber each other.
function mutate<T>(fn: (users: UserRecord[]) => Promise<T> | T): Promise<T> {
  const job = writeQueue.then(async () => {
    const users = await readAll();
    const result = await fn(users);
    await writeAll(users);
    return result;
  });
  writeQueue = job.catch(() => undefined);
  return job;
}

export async function findUserByEmail(email: string): Promise<UserRecord | undefined> {
  const users = await readAll();
  return users.find((u) => u.email === email.trim().toLowerCase());
}

export async function findUserById(id: string): Promise<UserRecord | undefined> {
  return (await readAll()).find((u) => u.id === id);
}

export async function findUserByResetHash(hash: string): Promise<UserRecord | undefined> {
  return (await readAll()).find((u) => u.resetTokenHash === hash && (u.resetExpires ?? 0) > Date.now());
}

export class EmailTakenError extends Error {}

export function createUser(input: Omit<UserRecord, "id" | "createdAt">): Promise<UserRecord> {
  return mutate((users) => {
    const email = input.email.trim().toLowerCase();
    if (users.some((u) => u.email === email)) throw new EmailTakenError();
    const user: UserRecord = { ...input, email, id: randomUUID(), createdAt: new Date().toISOString() };
    users.push(user);
    return user;
  });
}

export function updateUser(id: string, patch: Partial<Omit<UserRecord, "id" | "email" | "createdAt">>): Promise<UserRecord | undefined> {
  return mutate((users) => {
    const u = users.find((x) => x.id === id);
    if (u) Object.assign(u, patch);
    return u;
  });
}
