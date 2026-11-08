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
| `/account` | Signed-in only (client-side redirect to `/login` if not); shows name, email and a log-out button |

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

## Sample data
The hero's live feed and the dashboard preview use sample values and are labelled "sample data" / "Demo data" in the UI.
The real dashboard is the Databricks one in `../dashboard/`.
