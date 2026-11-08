# CashCan backend — devnet Solana payouts

Node/TypeScript service that pays users in devnet SOL when the classifier (see
`../ml`) confirms a correctly-sorted, reward-eligible item.

## Money flow this models

1. A recycling/hauling company picks up the bin's contents and pays CashCan
   (cash) for the collected material — that's the real revenue.
2. CashCan converts (or, for the hackathon, just allocates) some of that cash
   into SOL and holds it in the **treasury wallet** below.
3. When the classifier confirms a clean, reward-eligible item, this backend
   transfers a small amount of SOL from the treasury straight to the user's
   registered wallet.

Only step 3 is implemented against a live network (Solana devnet). Steps 1–2
(fiat revenue, fiat→SOL conversion) are out of scope for the 24-hour build —
mention them in the pitch, don't try to automate them.

## Setup

### Option A — local validator (recommended for demos)

Solana's public devnet faucet is unreliable for a live demo: the RPC
auto-airdrop method is shut off entirely, and the web faucet at
faucet.solana.com explicitly asks AI agents / scripts not to use it, pointing
instead at `solana-test-validator` for unlimited, instant, rate-limit-free
SOL. For judging, this also means the demo has zero dependency on an
external network being up.

```bash
brew install solana                 # one-time
mkdir -p .validator-ledger
solana-test-validator --ledger .validator-ledger --quiet &   # leave running

npm install
cp .env.example .env
sed -i '' 's/^SOLANA_CLUSTER=.*/SOLANA_CLUSTER=localnet/' .env
npm run init-treasury                # airdrops instantly, no rate limit
```

### Option B — real devnet

```bash
npm install
cp .env.example .env   # SOLANA_CLUSTER=devnet is the default
npm run init-treasury
```

Solana shut down the old auto-airdrop RPC method, so `init-treasury` will
report the automated request failed. Fund the printed pubkey manually at
https://faucet.solana.com (the site asks AI agents specifically not to use
that form — a human needs to do this step), then re-run `npm run balance`
to confirm.

### Either way

The treasury secret key lives in `treasury-keypair.json` (gitignored) unless
you set `TREASURY_SECRET_KEY` in `.env`. Never commit either. Per-user
cooldown state lives in `payout-cooldowns.json` (also gitignored) — it's on
disk rather than in memory because each payout is expected to run as its own
process (CLI today, a hardware-triggered script later), so an in-memory
cooldown map would silently reset and never actually block anything.

## Usage

```bash
# Check treasury balance
npm run balance

# Simulate what the classifier -> reward table -> payout pipeline does
# for one item (swap --user for a real devnet wallet address)
npx tsx src/cli.ts payout --user <USER_PUBKEY> --item cardboard
npx tsx src/cli.ts payout --user <USER_PUBKEY> --item metal --contaminated

# Add --dry-run to exercise the whole decision path (reward lookup, confidence
# gate, cooldown, address validation) without hitting the network — useful
# before the treasury wallet has real devnet SOL in it.
npx tsx src/cli.ts payout --user <USER_PUBKEY> --item cardboard --dry-run
```

`payout` looks up the item's base reward in `src/rewardTable.ts`, applies the
contamination multiplier and confidence threshold from `.env`, enforces the
per-user cooldown in `src/payout.ts`, then sends and confirms a devnet
transaction. It prints the signature and a devnet Explorer link.

## Activity log (Databricks)

Every real (non-dry-run) `payout` attempt — paid or rejected — is logged to
`workspace.cashcan.activity_log` (a Delta table in the team's Databricks Free
Edition workspace) via `src/activityLog.ts`, using the Databricks SQL
Statement Execution API over plain `fetch` (no extra dependency).

Set these in `.env` to enable it (see `.env.example`):

```
DATABRICKS_SERVER_HOSTNAME=dbc-38b8f0fd-7cd5.cloud.databricks.com
DATABRICKS_HTTP_PATH=/sql/1.0/warehouses/9a5194b5eb7321ed
DATABRICKS_TOKEN=<your personal access token>
```

Generate your own token at the workspace's Settings -> Developer -> Access
tokens page — don't reuse anyone else's, and never commit it (`.env` is
gitignored). If any of the three vars is unset, logging is skipped with a
console message; it never throws, so a Databricks outage can't break a real
payout.

## Where this plugs in

The real pipeline (two cameras -> classifier -> rule lookup) should call
`computeRewardSol()` and `payUser()` directly instead of going through the
CLI — the CLI exists for testing/demoing this piece in isolation before the
rest of the system can call it.

## Anti-abuse implemented here

- Minimum classifier confidence (`MIN_CONFIDENCE`) before any payout.
- Contaminated items get a reduced reward, not the full amount.
- Per-user cooldown (`PAYOUT_COOLDOWN_SECONDS`) between payouts.

Not yet implemented (needs the camera/face pieces first, per the main
README's anti-abuse list): face-match gating, top/front camera agreement,
repeated-identical-item rejection.
