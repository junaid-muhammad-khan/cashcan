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

export async function findUserByEmail(email: string): Promise<UserRecord | undefined> {
  const users = await readAll();
  return users.find((u) => u.email === email.trim().toLowerCase());
}

export async function findUserById(id: string): Promise<UserRecord | undefined> {
  return (await readAll()).find((u) => u.id === id);
}

export class EmailTakenError extends Error {}

export function createUser(input: Omit<UserRecord, "id" | "createdAt">): Promise<UserRecord> {
  // Serialize writes so two concurrent signups can't clobber each other.
  const job = writeQueue.then(async () => {
    const users = await readAll();
    const email = input.email.trim().toLowerCase();
    if (users.some((u) => u.email === email)) throw new EmailTakenError();
    const user: UserRecord = { ...input, email, id: randomUUID(), createdAt: new Date().toISOString() };
    users.push(user);
    await fs.mkdir(DATA_DIR, { recursive: true });
    const tmp = `${FILE}.${process.pid}.tmp`;
    await fs.writeFile(tmp, JSON.stringify(users, null, 2), { mode: 0o600 });
    await fs.rename(tmp, FILE);
    return user;
  });
  writeQueue = job.catch(() => undefined);
  return job;
}
