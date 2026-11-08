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
| `/signup` | Name, email, password, optional Solana wallet (base58 check), opt-in face enrollment, terms |
| `/login` | Email + password; `?next=/path` returns you where you were |
| `/account` | Signed-in only; shows the profile and a log-out button |

All motion is in `components/HomeMotion.tsx` and `components/AuthShell.tsx`. Content is visible
without JavaScript, and everything that moves is skipped when the visitor has reduced motion on.

## Auth (prototype)
- `app/api/auth/{signup,login,logout}` route handlers.
- Passwords hashed with scrypt (random salt per user); sessions are HMAC-signed, httpOnly, SameSite=Lax cookies (7 days).
- Users are stored in `.data/users.json` (gitignored). That only works on a single server with a persistent
  disk, so it won't survive serverless deploys such as Vercel. Swap `lib/users.ts` for a real database (e.g. Postgres/Supabase) before production.
- Not built yet: password reset, email verification, rate limiting on login, editing the wallet after sign-up,
  and linking an account to the face-enrollment flow in `face_api/`.

## Sample data
The hero's live feed and the dashboard preview use sample values and are labelled "sample data" / "Demo data" in the UI.
The real dashboard is the Databricks one in `../dashboard/`.
