# Prompt: connect the CashCan backend end to end

Copy everything below the line into a new coding session that has this repository (`junaid-muhammad-khan/cashcan`) checked out.

---

You are working on **CashCan**, a hackathon project: a smart bin that recognises a person by face, classifies the item they drop (cans / organics / waste), opens the right lid, and pays them cash back in SOL for recycling right. The pieces exist but are not connected. Your job is to **wire the whole backend together using the existing database (Databricks) and the existing frontend (Next.js site)**, so that a real drop at a bin ends with SOL in the user's wallet and the drop showing up on their dashboard and on the city dashboard.

Read `README.md`, `face_api/README.md`, `website/README.md`, `backend/README.md` and `databricks/*.sql` before changing anything. Work on a new branch, commit in small steps, and open a pull request at the end. Do not push to `main` directly.

## Decisions already made (do not re-open these)

1. **`face_api/` (Python/FastAPI, on Vercel) is the one main API.** The website and the bin only talk to it. `backend/` (Node/TypeScript) stops being a CLI and becomes only the Solana payout code, called by `face_api`.
2. **Reward rule: half the BC deposit, paid in SOL at the live rate.** A paying item earns **5¢ CAD** (half of the 10¢ BC deposit), converted to SOL at the live SOL/CAD rate **at the moment the payout is sent**. Organics and waste pay 0 for now. The website's Prices page and the backend must use **one source of truth** for these amounts.
3. **Payouts are instant, per item.** Right after the bin records a paying item, the payout is sent. Failures are retried automatically.
4. **Solana devnet.** Never mainnet. The treasury is funded with devnet SOL in advance (the public faucet is unreliable, so don't depend on it at request time).
5. **The payout runs as a Node API route on the same Vercel project** (inside the Next.js app in `website/`), called by `face_api` with a shared secret.
6. **No wallet yet → hold the reward.** If a recognised user drops a paying item but has no wallet saved, record the reward as **held**. When they save a wallet, pay all their held rewards automatically.
7. **Single source of truth for activity: `workspace.cashcan_app.interactions`.** `workspace.cashcan.activity_log` is retired (replace it with a view if anything still reads it).
8. **In scope:** the user dashboard on real data, and the city (Databricks AI/BI) dashboard on real data. **Out of scope:** a local rule table, the leaderboard page, admin/bin-management UI, contamination detection (the product no longer pitches contamination; don't build or display it).

## What exists today (verify each against the code)

- **Website** (`website/`, Next.js 15, deployed on Vercel at cashcan.biz). Auth is **Auth0 SPA, client-side only** (`components/Auth0ProviderWithNavigate.tsx`); pages that need login gate in an effect. It gets an Auth0 access token for the face API audience (`NEXT_PUBLIC_AUTH0_AUDIENCE`) and calls the face API through `/face-api/*` (`lib/faceApi.ts`, `lib/useProfile.ts`). `/dashboard` (`app/dashboard/`) renders `DashboardView` from **demo data** in `app/dashboard/data.ts` (a dev-only `?preview=1` shows demo props). `/prices` reads `lib/prices.ts` (container catalogue: BC deposit 10¢, cash back = deposit × `CASH_BACK_SHARE` 0.5) and has a reward calculator using the live rate from `app/api/rate/route.ts` (Coinbase → CoinGecko → Kraken, cached 60 s; helpers in `lib/rate.ts`).
- **Face API** (`face_api/`, FastAPI, Vercel service routed at `/face-api/*` per `vercel.json`). Endpoints: `/enroll`, `/pose`, `/match`, `/liveness/{id}/frame`, `/session/{token}`, `DELETE /users/{id}`, `GET/PUT /me` (Auth0 token; profile incl. `sol_wallet`, `face_enrolled`), `GET /leaderboard`, `POST /interactions` (bin, `X-Bin-Key`), `POST /interactions/{id}/payout` (bin reports a payout result). Accounts and interactions are in Databricks via `app/accounts.py`; face templates in `workspace.cashcan_faces`.
- **Bin** (`pi_client/`): identifies the person (match + liveness → session token), classifies the item, opens a lid, then calls `POST /interactions` (`pi_client/cashcan_pi/api.py`). Check what it sends; today it may send its own `reward_lamports`.
- **Payout code** (`backend/src/`): `payout.ts` (`payUser`, per-user cooldown stored in a **local JSON file**), `treasury.ts` (keypair from `TREASURY_SECRET_KEY` or a **local keypair file**), `rewardTable.ts` (flat 0.004 SOL for `cans`, 25% contaminated multiplier), `activityLog.ts` (writes `workspace.cashcan.activity_log`), `cli.ts`. Local files do not work on Vercel serverless.
- **Databricks** (`databricks/app_schema.sql`): `workspace.cashcan_app.users(user_id, auth0_sub, username, pseudonym, sol_wallet, created_at)`, `bins(bin_id, name, location)`, `interactions(interaction_id, user_id, session_id, bin_id, item_class, confidence, reward_lamports, payout_status pending|paid|failed|none, tx_signature, created_at)`, view `leaderboard`. Delta has no enforced keys; code uses `MERGE` for idempotency.
- **City dashboard** (`dashboard/`): `build_dashboard.py` + `deploy.py` build a Databricks AI/BI (Lakeview) dashboard over `activity_log`, currently pointed at a synthetic demo copy (`workspace.cashcan_demo.activity_log`).

## Target flow

```
bin drop ──> face_api POST /interactions  (X-Bin-Key; server computes the reward, never trusts the bin's amount)
               │  writes interactions row: reward_cents, status = none | held | pending
               │  if pending ──> claims it (pending → sending, atomic MERGE) ──> POST {SITE}/api/payout (shared secret)
               │                                   website Node route: live SOL/CAD rate → lamports → devnet transfer
               │                                   with memo "cashcan:<interaction_id>" → returns signature
               │  <── paid + tx_signature + lamports + cad_per_sol   (or failed + error)
user saves wallet (PUT /me) ──> all held rows for that user → pending → paid, same path
Vercel cron every minute ──> reconcile: retry failed (with backoff, max attempts), resolve stuck "sending" by memo lookup
website /dashboard ──> face_api GET /me/activity (Auth0) ──> real totals, recent drops, statuses
city dashboard ──> Databricks view over interactions (+ users for pseudonyms, + bins)
```

## Work to do

### 1. One reward table
- Make `face_api` the canonical owner of reward amounts (e.g. `face_api/app/rewards.py`): per item class → `cents` (`cans`: 5, `organics`: 0, `waste`: 0), derived from the deposit (10¢) × share (0.5). Expose it read-only as `GET /rewards`.
- Have the website's Prices page read `GET /face-api/rewards` (server-side, revalidated every few minutes) with `lib/prices.ts` as the fallback, **and** add a test that fails if the two disagree. The container catalogue stays as is: every container type in it maps to the classifier's `cans` class.
- Remove the contaminated multiplier and the flat 0.004 SOL from the payout path.

### 2. Recording interactions (face_api)
- `POST /interactions`: ignore any reward the bin sends. Compute `reward_cents` from `item_class` via the reward table, and only when there is a live verified session (`session_token` → user) **and** `confidence ≥ MIN_CONFIDENCE` (env, default 0.75). Otherwise `reward_cents = 0`, status `none`.
- Enforce a per-user cooldown server-side from the interactions table (`PAYOUT_COOLDOWN_SECONDS`, default 30): a paying drop inside the cooldown is recorded with reward 0 and a reason. Replace the JSON-file cooldown.
- Status: `none` (no reward), `held` (reward but no wallet), `pending` (reward + wallet). Keep `interaction_id` idempotent: a retried request returns the existing row and never pays twice.
- If `pending`, trigger the payout immediately (step 3) within the request, with a short timeout (~8 s). If it times out, leave the row as `sending`; the reconcile job finishes it.
- Update `pi_client` only as needed (stop sending its own reward; show the server's reward/status in its output).

### 3. Payout route (website, Node)
- Move the reusable parts of `backend/src/payout.ts` and `treasury.ts` into the website (e.g. `website/lib/solana/`), with `@solana/web3.js`. Keypair only from `TREASURY_SECRET_KEY` (base58, Vercel env), RPC from `SOLANA_RPC_URL` (devnet). No files on disk.
- `POST /api/payout` (Node runtime), authenticated by `Authorization: Bearer ${PAYOUT_SECRET}` (constant-time compare). Body: `interaction_id`, `to` (wallet), `reward_cents`. It reads the live rate using the same logic as `app/api/rate/route.ts` (refactor that into a shared function), converts cents → CAD → SOL → lamports, sends the transfer with memo `cashcan:<interaction_id>`, waits for `confirmed`, and returns `{ signature, lamports, cad_per_sol, rate_source }`.
- Before sending, check the treasury balance; if it can't cover the payout plus fees, return a clear error (and keep the row retryable). Never send without a valid base58 wallet address.
- Keep `backend/` working as a thin wrapper or document that it is superseded; don't leave two divergent payout implementations.

### 4. Database changes (Databricks)
- Add a migration file (e.g. `databricks/002_interactions_payouts.sql`) that **adds columns, never drops data**: `reward_cents INT`, `lamports BIGINT`, `cad_per_sol DOUBLE`, `rate_source STRING`, `payout_error STRING`, `payout_attempts INT`, `paid_at TIMESTAMP`, `updated_at TIMESTAMP`, `reason STRING`. Widen `payout_status` to `none | held | pending | sending | paid | failed`. Keep `reward_lamports` for compatibility (fill it with the paid lamports).
- State changes use `MERGE … WHEN MATCHED AND payout_status = '<expected>'` so two workers can't both pay the same row.
- Update the `leaderboard` view to use the new columns if needed.
- Replace `workspace.cashcan.activity_log` with a view over `interactions` for anything that still reads it; stop writing to it (`backend/src/activityLog.ts`).

### 5. Held rewards
- When `PUT /me` saves a valid wallet, move that user's `held` rows to `pending` and pay them (same path, sequentially, respecting the treasury check). Return how many were queued so the website can say so.

### 6. Reconcile job
- A Vercel cron (`vercel.json`) every minute calling a protected endpoint (face_api or website, your choice; protect it with `CRON_SECRET`). It retries `failed` rows with backoff up to a max attempt count, and resolves rows stuck in `sending` for more than ~2 minutes by searching the treasury's recent transactions for the `cashcan:<interaction_id>` memo (mark `paid` if found, otherwise back to `pending`). It must be safe to run twice at the same time.

### 7. User dashboard on real data (website)
- New face_api endpoint `GET /me/activity?range=today|week|30d` (Auth0): totals (items, paid SOL, paid CAD at the rate stored on each row, held amount, pending count), counts by bin (cans / organics / waste), and the most recent drops (item class, bin, time, reward, status, tx signature).
- Wallet balance: a small website route (or face_api endpoint) reading the user's devnet balance from `SOLANA_RPC_URL`.
- Replace `app/dashboard/data.ts` as the data source in `DashboardView`; keep the current design and the dev-only `?preview=1` demo. **Remove any card or chart the real data can't support** (don't show invented metrics). Add proper empty, loading and error states (a brand-new user has no drops). Show held rewards with a prompt to add a wallet, and link paid drops to the devnet explorer.

### 8. City dashboard on real data (Databricks)
- Create a view (e.g. `workspace.cashcan_app.city_activity`) joining interactions, bins and users (pseudonym only, never username or email): time, bin, item class, recognised or not, reward cents, lamports, payout status.
- Update `dashboard/build_dashboard.py` to read it: drop the contamination widgets; show items per day by bin, recognised vs unrecognised drops, rewards paid (SOL and CAD), payout status mix (paid / held / failed), activity per bin location, and top sorters by pseudonym. Redeploy with `dashboard/deploy.py` and give the dashboard link.
- Note: in earlier work the account used for the dashboard lacked `USE SCHEMA` on some `workspace.cashcan*` schemas. If you hit a permission error, stop and report the exact `GRANT` needed instead of working around it.

## Environment variables (document all of them in the READMEs and `.env.example` files, never commit values)

- face_api: existing Databricks + Auth0 vars, `BIN_API_KEYS`, plus `PAYOUT_URL` (the website's `/api/payout`), `PAYOUT_SECRET`, `MIN_CONFIDENCE`, `PAYOUT_COOLDOWN_SECONDS`, `CRON_SECRET`.
- website: existing Auth0 vars, plus `TREASURY_SECRET_KEY`, `SOLANA_RPC_URL`, `PAYOUT_SECRET`, `CRON_SECRET`.

## Rules

- Don't change face recognition, liveness or enrollment behaviour, and don't break any page that works today.
- Never log or commit secrets, private keys or full tokens. Never use mainnet.
- Every money-moving step must be idempotent and safe to retry or run concurrently.
- Keep the face_api Vercel bundle under its size limit (see `face_api/requirements.txt` comments).
- If something in this prompt conflicts with the code, or you need a product decision, **stop and ask** instead of guessing. Examples: the exact cooldown, a daily payout cap, what the bin should display after a held reward.

## Tests and proof

- face_api pytest: reward calculation, status transitions (none / held / pending / sending / paid / failed), idempotent `POST /interactions`, cooldown, held → paid on wallet save, the reconcile job's stuck-row handling, `/me/activity` shape and auth.
- website: unit tests for cents → lamports conversion and for `/api/payout` auth and validation (mock the Solana connection).
- An end-to-end script (e.g. `scripts/e2e_devnet.sh` or `.py`) that, against a deployed preview: creates or uses a test user with a devnet wallet, posts a fake bin interaction with a test bin key, and checks that the row becomes `paid` with a real devnet signature, that the user's `/me/activity` shows it, and that the city view includes it. Run it and paste the output in the PR.
- Run every existing test suite before opening the PR and report the results honestly, including anything that fails or was skipped.

## Deliverables

A pull request that contains: the code changes above, the migration SQL, updated READMEs and `.env.example` files, the tests, the e2e script and its output, the redeployed city dashboard link, and a short "how to run the demo" section (fund the treasury, set the env vars, run the e2e script).
