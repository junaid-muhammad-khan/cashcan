import { NextResponse } from "next/server";
import { hashResetToken, newResetToken } from "@/lib/auth";
import { findUserByEmail, updateUser } from "@/lib/users";
import { validateEmail } from "@/lib/validation";

export const runtime = "nodejs";

const RESET_MINUTES = 30;

export async function POST(req: Request) {
  const body = await req.json().catch(() => null);
  const email = String(body?.email ?? "");
  const err = validateEmail(email);
  if (err) return NextResponse.json({ fieldErrors: { email: err } }, { status: 422 });

  const user = await findUserByEmail(email);
  if (user) {
    const token = newResetToken();
    await updateUser(user.id, { resetTokenHash: hashResetToken(token), resetExpires: Date.now() + RESET_MINUTES * 60_000 });
    const link = new URL(`/reset-password?token=${token}`, req.url).toString();
    // No email provider is wired up yet. Until one is, the link is written to the
    // server log so the flow can be demoed. Replace this with a real email send.
    console.log(`[cashcan] password reset link for ${user.email} (valid ${RESET_MINUTES} min): ${link}`);
  }
  // Same response whether or not the account exists, so this can't be used to find accounts.
  return NextResponse.json({ ok: true });
}
