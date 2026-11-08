# CashCan website

Next.js 15 (App Router) + GSAP/ScrollTrigger marketing site with working email/password sign-up and log-in.
The visual reference is the canvas design in `design/`.

## Run it

```bash
npm install
cp .env.example .env.local   # then set AUTH_SECRET (32+ chars)
npm run dev                  # http://localhost:3000
```

`npm run build && npm start` for a production build (AUTH_SECRET is required in production).

## Pages
| Route | What it is |
|---|---|
| `/` | Home page with scroll-triggered reveals, untilting hero mockup, floating cards, live drop feed, drifting gradient background, count-up numbers, pinned five-step "how it works" story, and a dashboard preview that expands on scroll |
| `/signup` | Name, email, password (strength bar), optional Solana wallet (base58 check), opt-in face enrollment, terms. The side panel's three-step tracker ticks off as you fill the form |
| `/login` | Email + password, "Keep me logged in for 7 days" (off = browser-session cookie, 12 h max), forgot-password link; `?next=/path` returns you where you were |
| `/forgot-password` | Asks for an email and always answers the same way, so it can't reveal which emails have accounts |
| `/reset-password?token=…` | New password + confirm, with strength bar; single-use token valid 30 minutes, logs you in when saved |
| `/account` | Signed-in only; shows the profile and a log-out button |

All motion is in `components/HomeMotion.tsx` and `components/AuthShell.tsx`. Content is visible
without JavaScript, and everything that moves is skipped when the visitor has reduced motion on.

## Auth (prototype)
- `app/api/auth/{signup,login,logout}` route handlers.
- Passwords hashed with scrypt (random salt per user); sessions are HMAC-signed, httpOnly, SameSite=Lax cookies (7 days).
- Users live in Databricks (`workspace.cashcan_web.users`, created by `../databricks/website_users.sql`) whenever `DATABRICKS_HOST`,
  `DATABRICKS_TOKEN` and `DATABRICKS_WAREHOUSE_ID` are set (use these on Vercel). Without them, local dev falls back to `.data/users.json`
  (gitignored; not usable on serverless hosts). Code: `lib/users.ts` picks the store; `lib/users-databricks.ts` talks to the SQL Statement API.
- Password reset: only a SHA-256 of the token is stored; tokens are single-use and expire after 30 minutes.
  **No email provider is connected yet**: the reset link is printed to the server log
  (`[cashcan] password reset link for …`). Hook `app/api/auth/forgot/route.ts` up to an email service
  (e.g. Resend) before real users rely on it.
- Not built yet: email verification, rate limiting on login and reset requests, editing the wallet after sign-up,
  and linking an account to the face-enrollment flow in `face_api/`.

## Sample data
The hero's live feed and the dashboard preview use sample values and are labelled "sample data" / "Demo data" in the UI.
The real dashboard is the Databricks one in `../dashboard/`.
