// Shared by the forms (blur validation) and the API routes (authoritative check).
export const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
// Solana addresses are base58 public keys, 32–44 characters.
export const SOLANA_RE = /^[1-9A-HJ-NP-Za-km-z]{32,44}$/;

export type FieldName = "name" | "email" | "password" | "wallet" | "terms";
export type FieldErrors = Partial<Record<FieldName, string>>;

export function validateEmail(v: string): string | undefined {
  if (!v.trim()) return "Enter your email address.";
  if (!EMAIL_RE.test(v.trim())) return "That email looks incomplete, for example name@example.com.";
}

export function validatePassword(v: string, forSignup: boolean): string | undefined {
  if (!v) return "Enter your password.";
  if (forSignup && v.length < 8) return "Use at least 8 characters.";
  if (forSignup && v.length > 200) return "Use 200 characters or fewer.";
}

export function validateName(v: string): string | undefined {
  if (!v.trim()) return "Enter your name so the bin can greet you.";
  if (v.trim().length > 80) return "Use 80 characters or fewer.";
}

export function validateWallet(v: string): string | undefined {
  if (v.trim() && !SOLANA_RE.test(v.trim())) {
    return "Solana addresses are 32–44 letters and numbers. Paste it again, or leave it blank for now.";
  }
}
