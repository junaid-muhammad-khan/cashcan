import { NextResponse } from "next/server";
import { createSessionToken, hashPassword, hashResetToken, SESSION_COOKIE, sessionCookieOptions } from "@/lib/auth";
import { findUserByResetHash, updateUser } from "@/lib/users";
import { validatePassword } from "@/lib/validation";

export const runtime = "nodejs";

export async function POST(req: Request) {
  const body = await req.json().catch(() => null);
  const token = String(body?.token ?? "");
  const password = String(body?.password ?? "");
  const pwErr = validatePassword(password, true);
  if (pwErr) return NextResponse.json({ fieldErrors: { password: pwErr } }, { status: 422 });

  const user = token ? await findUserByResetHash(hashResetToken(token)) : undefined;
  if (!user) {
    return NextResponse.json(
      { error: "This reset link has expired or was already used. Request a new one and use it within 30 minutes." },
      { status: 400 },
    );
  }
  await updateUser(user.id, { passwordHash: await hashPassword(password), resetTokenHash: null, resetExpires: null });
  const { token: session, expires } = createSessionToken(user.id, true);
  const res = NextResponse.json({ ok: true });
  res.cookies.set(SESSION_COOKIE, session, sessionCookieOptions(expires, true));
  return res;
}
