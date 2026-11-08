# CashCan backend — devnet treasury tools

Payouts no longer run here. The flow is:

1. The bin records a drop with the face API (`POST /face-api/interactions`).
2. The face API decides the reward (`face_api/app/rewards.py`: 5¢ CAD per can, half the BC deposit) and keeps its state in Databricks.
3. The face API calls the website's Node route `POST /api/payout` (`website/app/api/payout`, `website/lib/solana/`), which converts the cents to SOL
   at the live rate and sends the devnet transfer from the treasury, tagged with the memo `cashcan:<interaction_id>`.

This folder is the operator CLI for the treasury that route pays from. The old per-process payout code (JSON-file cooldown, flat 0.004 SOL reward
table, contamination multiplier, `activity_log` writer, `classify-and-pay`) was removed so there is one payout implementation only.

## Commands

```bash
npm install
cp .env.example .env
npm run init-treasury                 # creates treasury-keypair.json (gitignored) if needed, prints the address and devnet balance
npm run balance
npm run cli -- export-secret          # prints the base58 key for the TREASURY_SECRET_KEY env var on Vercel (keep it private)
PAYOUT_URL=https://cashcan.biz/api/payout PAYOUT_SECRET=... npm run cli -- test-payout --to <devnet wallet> --cents 5
```

## Funding the treasury (do this before a demo)
The devnet RPC faucet is closed, so a person has to fund the treasury at https://faucet.solana.com (paste the address from `init-treasury`),
or send devnet SOL from another devnet wallet. Each paid can costs about 0.0004 SOL at today's rate plus a 0.000005 SOL fee, so 1 SOL covers
about 2,000 cans. When the treasury runs low, `/api/payout` answers `treasury_low` and the face API retries later (see `face_api/README.md`).

Devnet only: `SOLANA_RPC_URL` must not point at mainnet. Never commit `.env`, `treasury-keypair.json` or a key.
