import { NextResponse } from "next/server";
import { createSessionToken, hashPassword, publicUser, SESSION_COOKIE, sessionCookieOptions } from "@/lib/auth";
import { createUser, EmailTakenError } from "@/lib/users";
import { validateEmail, validateName, validatePassword, validateWallet, type FieldErrors } from "@/lib/validation";

export const runtime = "nodejs";

export async function POST(req: Request) {
  const body = await req.json().catch(() => null);
  if (!body || typeof body !== "object") {
    return NextResponse.json({ error: "We couldn't read that request. Try again." }, { status: 400 });
  }

  const name = String(body.name ?? "");
  const email = String(body.email ?? "");
  const password = String(body.password ?? "");
  const wallet = String(body.wallet ?? "");
  const fieldErrors: FieldErrors = {};
  const checks: [keyof FieldErrors, string | undefined][] = [
    ["name", validateName(name)],
    ["email", validateEmail(email)],
    ["password", validatePassword(password, true)],
    ["wallet", validateWallet(wallet)],
    ["terms", body.terms === true ? undefined : "Accept the terms to create your account."],
  ];
  for (const [k, msg] of checks) if (msg) fieldErrors[k] = msg;
  if (Object.keys(fieldErrors).length) return NextResponse.json({ fieldErrors }, { status: 422 });

  try {
    const user = await createUser({
      name: name.trim(),
      email,
      passwordHash: await hashPassword(password),
      walletAddress: wallet.trim() || null,
      faceOptIn: body.faceOptIn === true,
    });
    const { token, expires } = createSessionToken(user.id);
    const res = NextResponse.json({ user: publicUser(user) }, { status: 201 });
    res.cookies.set(SESSION_COOKIE, token, sessionCookieOptions(expires));
    return res;
  } catch (err) {
    if (err instanceof EmailTakenError) {
      return NextResponse.json(
        { fieldErrors: { email: "An account with this email already exists. Log in instead." } },
        { status: 409 },
      );
    }
    throw err;
  }
}
