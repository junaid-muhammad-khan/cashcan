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
| `/` | Home page with scroll-triggered reveals, untilting hero mockup, floating cards, live drop feed, drifting gradient background, count-up numbers, pinned five-step "how it works" story, and a dashboard preview that expands on scroll |
| `/signup` | Two-panel signup design; the right panel (`components/AuthPanel.tsx`) has "Continue with Google" / "Continue with email", both redirecting to Auth0 Universal Login with `screen_hint: signup` |
| `/login` | Two-panel login design, same `AuthPanel`; `?next=/path` returns you where you were after login |
| `/enroll` | Face match setup, where sign-up lands. Consent (+ Solana wallet if the profile has none, saved with `PUT /me`), live webcam with an oval guide, three auto-captured angles (straight, left, right), `POST /enroll` to the face API, then a one-frame `POST /match` test showing the similarity score. Handles camera blocked/missing, unclear frames (per-angle tips from the API's quality checks) and already-enrolled (409). Skippable |
| `/dashboard` | Signed-in only (client-side redirect to Auth0 if not); where login and signup land. Recent detections (click to expand), rewards card (pending configuration), four summary cards and the sorting-outcomes chart. The date-range menu updates every number; clicking a bar filters the detections. **All figures are demo data** (`app/dashboard/data.ts`) until drops are linked to accounts |
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
- Not carried over from the old custom auth: the wallet-address and face-opt-in fields that used to live in
  the account store have no replacement yet. `/account` shows them as static placeholders ("Not linked yet" /
  "Not enrolled"). Reintroducing them means a small profile store keyed by the Auth0 `sub` claim (e.g. verify
  the ID token server-side with `jose` + Auth0's JWKS endpoint in an API route — Databricks, set up in
  `../databricks/website_users.sql` for the previous password-based accounts, would work for this too), plus
  linking that to the face-enrollment flow in `face_api/`.

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

## Sample data
The hero's live feed and the dashboard preview use sample values and are labelled "sample data" / "Demo data" in the UI.
The real dashboard is the Databricks one in `../dashboard/`.
