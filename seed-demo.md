# CashCan (step 1: register / sign in + dashboard mockup)

Django + SQLite backend, React (Vite) frontend, Auth0 login. Skeleton for iterative building.

## Run it

```bash
# terminal 1: backend
cd backend
pip install -r requirements.txt
cp .env.example .env            # leave AUTH0_* empty to use the dev login
python manage.py migrate
python manage.py seed_demo      # placeholder items, fake leaderboard users, a demo user with data
python manage.py runserver      # :8000

# terminal 2: frontend
cd frontend
npm install
npm run dev                     # :5173  <- open this one
```

Open http://localhost:5173. Without Auth0 set there are two dev logins: the seeded demo user
(dashboard with data) and a new user with no onboarding (consent -> face -> wallet -> dashboard).
Both are DEBUG-only and switch off automatically once AUTH0_* is configured.

Auth0 setup: create a Regular Web Application, then set
Allowed Callback URL `http://localhost:5173/auth/callback`, Allowed Logout URL `http://localhost:5173`,
and fill `AUTH0_DOMAIN / CLIENT_ID / CLIENT_SECRET` in `backend/.env`. Everything goes through the
Vite origin (it proxies /api and /auth to Django) so the session cookie and callback share one origin.

## Layout

```
backend/core/models.py      MVP schema (trimmed from cashcan-schema.md)
backend/core/services.py    reward_for() and attribute_event(): payout logic, idempotent
backend/core/views.py       /api/me, onboarding/*, dashboard
backend/core/auth_views.py  Auth0 OIDC login/callback/logout + DEBUG-only dev login
frontend/src/pages/         Login, Onboarding (consent -> face -> wallet), Dashboard
```

## Decisions made

- **Async identity.** The bin opens from the local classifier and never waits for identification.
  A `SortingEvent` arrives with `identity_status="pending"`; when the face lookup returns, call
  `services.attribute_event(event, user, score)`, which sets the user and creates one pending `Payout`.
  `services.mark_unknown(event)` covers no-match. Calling attribute twice cannot double-pay.
- **Payout split.** Interpreted as: contaminated items pay 50% of the clean amount
  (`CONTAMINATED_REWARD_FRACTION=0.5`, one setting). Clean amount per item is `ItemClass.base_reward_lamports`.
- **MVP scope.** No extra validation: anti-abuse checks, wallet signature verification, and liveness are
  marked TODO in code. Face scan is a stub (creates the enrollment pointer, no embedding yet).
- **Item rules in `seed_demo` are placeholders** with `verified_at` left null. Verify against the
  Recycle BC / Metro Vancouver lists before relying on them.

## Next steps (suggested order)

1. Device endpoint: `POST /api/device/events` (device API key, event UUID, upsert) + `POST /api/device/identify`.
2. Real face enrollment: browser capture -> embedding -> Databricks table + pointer in `FaceEnrollment`.
3. Payout worker: send devnet SOL, move `Payout.status` pending -> submitted -> confirmed.
4. Sync events to Databricks.
