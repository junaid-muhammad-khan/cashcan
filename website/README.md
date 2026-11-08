# CashCan website

Next.js 15 (App Router) + GSAP/ScrollTrigger marketing site, with sign-up and log-in via Auth0.
The visual reference is the canvas design in `design/`.

## Run it

```bash
npm install
cp .env.example .env.local   # already has the dev Auth0 domain/clientId, override if needed
npm run dev                  # http://localhost:3000
```

`npm run build && npm start` for a production build.

In the Auth0 Dashboard, the Application's **Allowed Callback URLs**, **Allowed Logout URLs**, and
**Allowed Web Origins** must include whatever origin you're actually running on (`http://localhost:3000`
for local dev, `https://cashcan.biz` in production) or login/logout will fail with a callback mismatch.

## Pages
| Route | What it is |
|---|---|
| `/` | Home page with scroll-triggered reveals, an illustrative hero mockup (explicitly labelled as example, not live, data), drifting gradient background, count-up numbers, and a pinned five-step "how it works" story |
| `/signup` | Two-panel signup design; the right panel (`components/AuthPanel.tsx`) has "Continue with Google" / "Continue with email", both redirecting to Auth0 Universal Login with `screen_hint: signup` |
| `/login` | Two-panel login design, same `AuthPanel`; `?next=/path` returns you where you were after login |
| `/enroll` | Face match setup, where sign-up lands. Consent (+ Solana wallet if the profile has none, saved with `PUT /me`), live webcam with an oval guide, three auto-captured angles (straight, left, right), `POST /enroll` to the face API, then a one-frame `POST /match` test showing the similarity score. Handles camera blocked/missing, unclear frames (per-angle tips from the API's quality checks) and already-enrolled (409). Skippable |
| `/dashboard` | Signed-in only. The user's real drops from `GET /face-api/me/activity` (`lib/activity.ts`): SOL paid (and its CAD value at the rate stored on each payout), held and on-the-way rewards, recent drops with status and a devnet explorer link, items per bin over time, wallet with its devnet balance (`/api/balance`). Loading, empty (new user) and error states. `?preview=1` shows demo data in local dev only (`app/dashboard/data.ts`) |
| `/account` | Signed-in only (client-side redirect to `/login` if not); shows name, email, a link back to the dashboard and a log-out button ("Profile" in the dashboard header) |

All motion is in `components/HomeMotion.tsx` and `components/AuthShell.tsx`. Content is visible
without JavaScript, and everything that moves is skipped when the visitor has reduced motion on.

## Auth (Auth0)
- `@auth0/auth0-react` via `components/Auth0ProviderWithNavigate.tsx`, mounted in `app/layout.tsx`. Auth state
  (`isAuthenticated`, `user`, `loginWithRedirect`, `logout`) is client-side only — there is no server session,
  so pages that need to gate on auth (`/account`) are Client Components that redirect in a `useEffect` once
  `useAuth0()` resolves, rather than a server-side `redirect()`.
- `/signup` and `/login` use a custom-designed right panel (`components/AuthPanel.tsx` + `.module.css`) with
  two buttons — "Continue with Google" and "Continue with email" — that both call `loginWithRedirect()` from
  `@auth0/auth0-react`, redirecting to Auth0's hosted Universal Login (Google goes straight to Google's own
  account picker via `connection: "google-oauth2"`; email goes to Auth0's database-connection screen, which
  itself handles password, magic link and passkey). No embedded widget, no cross-origin auth config, no extra
  bundler workarounds — this app previously tried embedding the `auth0-lock` widget for a true one-page flow
  (kept in git history if that's worth revisiting), but it added real complexity (a bundler bug in `auth0-js`
  needing a webpack workaround, and a third-party-cookie reliability caveat for the cross-origin auth flow)
  without look-identical wins, so it was replaced with this simpler redirect-based panel.
- Credentials, password reset, and signup are entirely handled by Auth0's own hosted pages and APIs — this
  app's own code never sees a password.
- `/account` still shows wallet address and face-match enrollment as static placeholders ("Not linked yet" /
  "Not enrolled") — **this website doesn't call it yet, but a real backend for it now exists**:
  `face_api/app/accounts.py` has a working Databricks-backed `users`/`interactions`/`leaderboard` schema
  (`databricks/app_schema.sql`), with `GET /me` (profile + wallet, Auth0-token-verified) and `GET /leaderboard`
  endpoints already deployed (`face_api`, routed under `/face-api/*` per `vercel.json`). Wiring `/account` up to
  `GET /me` — and possibly a real leaderboard somewhere on the site — is the next real step here, not a
  from-scratch build.

## Rewards and payouts (server routes)
| Route | Who calls it | What |
|---|---|---|
| `POST /api/payout` | the face API only (`Authorization: Bearer $PAYOUT_SECRET`) | `{interaction_id, to, reward_cents}` -> live SOL/CAD rate -> lamports -> devnet transfer from the treasury with memo `cashcan:<interaction_id>` -> `{signature, lamports, cad_per_sol, rate_source}`. Checks the memo first and returns the existing transfer instead of paying twice; refuses a bad wallet, more than 100¢, or a treasury that can't cover it (`503 treasury_low`, retried later by the face API) |
| `GET /api/payout?interaction_id=` | the face API's reconcile job | `{found, signature, lamports}` by memo |
| `GET /api/rate` | the browser | live SOL/CAD (Coinbase -> CoinGecko -> Kraken, `lib/rateQuote.ts`, the same code the payout uses) |
| `GET /api/balance?address=` | the dashboard | devnet balance of a wallet |

**Demo mode** (`PAYOUT_MODE=demo`, or no `TREASURY_SECRET_KEY`): the route does everything except the transfer and answers with a placeholder
signature `demo_<hash>` (`simulated: true`), so the whole flow (paid status, dashboards, city view) works without a funded treasury. The dashboard
labels these "Demo payout: no SOL was sent".

Code: `lib/payoutHandler.ts`, `lib/solana/` (treasury key only from `TREASURY_SECRET_KEY`, RPC from `SOLANA_RPC_URL`, mainnet refused).
`/prices` reads the reward table from `GET /face-api/rewards` (revalidated every 5 minutes), with `lib/prices.ts` as the fallback.
Tests: `npm test` (vitest: cents -> lamports, the route's auth and validation with a mocked Solana connection).
Server env vars (Vercel, never `NEXT_PUBLIC_`): `TREASURY_SECRET_KEY`, `SOLANA_RPC_URL`, `PAYOUT_SECRET`, `CRON_SECRET` (see `.env.example`).

## Face match setup (`/enroll`)
- Talks to the face API in `../face_api` through `/face-api/*` (`lib/faceApi.ts`). Vercel routes that path to the
  face service (`../vercel.json`); for local dev, start the API (`uvicorn app.main:app_factory --factory --port 8000`
  in `face_api/`) and set `FACE_API_ORIGIN=http://localhost:8000` so `next.config.mjs` proxies it.
- Identity: with `NEXT_PUBLIC_AUTH0_AUDIENCE` set (same value as the face API's `AUTH0_AUDIENCE`), the page sends an
  Auth0 access token and the API takes the user and wallet from the account. Without it, the API must run without
  Auth0 and the page sends a user id derived from the Auth0 `sub` plus the wallet typed on the page.
- The API stores 512-number embeddings only; the page never uploads anything but the three JPEG frames and one test frame.
- Not verified end to end in production: whether Vercel's `/face-api` rewrite strips the prefix before it reaches FastAPI
  (if it doesn't, the API's routes need a `/face-api` root path), and the Auth0 API/audience setup.
- Tested locally against the real face API (SQLite store, Auth0 off) with a fake webcam: enroll, match test,
  re-enroll refused (409) and a no-face scan (per-angle tips) all behave as described.

## Sample / illustrative content
The homepage's old "Bin Activity" section (fabricated 14-day charts, no real data behind them) has been removed
entirely — it's been replaced by the real `/dashboard` page above, which now shows the signed-in user's real drops. The hero's "Example drops" mock panel is static illustrative content, explicitly labelled
as such in the UI (not live, not historical). The "How an item flows through CashCan" section's example numbers
(confidence score, cooldown timer, etc.) are a labelled walkthrough of the decision logic, not a claim of actual
usage history. Real per-drop activity lands in the Databricks schema from the Auth0 section above via `face_api`.
