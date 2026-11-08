import { NextResponse } from "next/server";
import { createSessionToken, publicUser, SESSION_COOKIE, sessionCookieOptions, verifyPassword } from "@/lib/auth";
import { findUserByEmail } from "@/lib/users";

export const runtime = "nodejs";

export async function POST(req: Request) {
  const body = await req.json().catch(() => null);
  const email = String(body?.email ?? "");
  const password = String(body?.password ?? "");
  const user = email ? await findUserByEmail(email) : undefined;
  // Same message whether the email or the password is wrong, so the form can't be used to probe for accounts.
  if (!user || !(await verifyPassword(password, user.passwordHash))) {
    return NextResponse.json(
      { error: "That email and password don't match an account. Check both, or create an account." },
      { status: 401 },
    );
  }
  const { token, expires } = createSessionToken(user.id);
  const res = NextResponse.json({ user: publicUser(user) });
  res.cookies.set(SESSION_COOKIE, token, sessionCookieOptions(expires));
  return res;
}
