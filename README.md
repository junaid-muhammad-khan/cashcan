# CashCan

**Canada sent a record 26.6 million tonnes of waste to disposal in 2022. Plenty of it could have been recycled. CashCan is a smart bin that pays you to recycle right.**

> Hackathon project (24 hours, HackCamp 2026). Theme: solve a problem in this world.
> **Status: in progress.** Built: the website (live at cashcan.biz), face enrollment and match (`face_api/`), the bin controller that identifies the person, classifies the item and opens the right lid (`pi_client/ --classify`, tested on a laptop webcam), the end-to-end payout (the face API decides the reward and the website's `/api/payout` sends devnet SOL, with retries), the user dashboard and the city dashboard on real data (`dashboard/`). **Not done yet:** the local rule table and the real bin hardware (lids, camera). Nothing has run on the real bin yet.

---

## The problem

In 2022, Canada generated **36.5 million tonnes** of solid waste. Only **9.9 million tonnes (about 27%)** was recycled or composted. The other **26.6 million tonnes** went to landfill or incineration, the most since tracking began in 2002.

Sources: [Statistics Canada](https://statcan.gc.ca/o1/en/plus/6850-less-diversion-and-more-non-residential-sources-push-canadas-waste-disposal-new-high-2022), [Environment and Climate Change Canada](https://www.canada.ca/en/environment-climate-change/services/environmental-indicators/solid-waste-diversion-disposal.html), summarized by [madeinca.ca](https://madeinca.ca/recycling-canada-statistics/). (The 26.6M figure is *all* disposed waste, not only recyclables. Say it that way in the pitch.)

Why so much recyclable material still ends up in the garbage:

- **No reason to bother.** Recycling right takes effort, and nobody gets anything for it. Signage and outreach help, but they don't change the habit.
- **The rules are confusing and local.** In Metro Vancouver, an item labelled "compostable" may not be accepted in the green bin. Food-soiled paper and foodware confuse people.
- **Contamination wastes the effort of people who do sort.** One greasy container can ruin a whole batch, so correctly sorted material goes to landfill too.
- **Existing smart bins sort by material** (plastic, paper, metal, glass), not by what your city actually accepts.

## Our solution

**Pay people, instantly, for every item they recycle correctly.** Then make sure the reward only goes to items that will actually be recycled.

A CashCan bin:

1. **Recognises you** with an opt-in face match and a head-turn liveness check, so the reward goes to your wallet without a card or phone.
2. **Identifies the item** (organics / cans / waste) and **opens the right lid**, so the item lands in the right container. The goal is to decide by **local Metro Vancouver rules**, not just by material.
3. **Pays you cash back in SOL** for reward-eligible items (today: cans, the BC Return-It deposit containers).
4. **Logs every decision** to Databricks, so cities and haulers can see what goes where and what people get wrong.

**Who pays for the rewards:** the recycling or hauling company that collects the bin pays for the sorted material. CashCan converts part of that revenue into SOL to fund the reward wallet. Cleaner material is worth more, so the incentive pays for itself.

**Our edge:** a direct, per-item incentive to recycle, with the bin itself routing each item to the right container, so the money goes to sorting that works. We searched and found no product doing exactly this. That's a search result, not proof that none exists.

---

## How it works

```
Sign up on cashcan.biz -> enroll face -> add Solana wallet on the profile page
   -> At the bin: face match identifies the user (with a head-turn liveness check)
   -> The same camera sees the item held in the item region
   -> Classifier: organics / cans / waste (3-look average; unsure -> waste)
   -> The bin opens that lid
   -> Interaction recorded (POST /interactions): the server decides the reward (5¢ CAD per can)
   -> Paid at once in devnet SOL at the live rate -> Databricks -> user dashboard + city dashboard
   -> next item
```

How the pieces connect in code:

```
website sign-up -> face_api /enroll (consent, 1-3 photos, templates only)
                          face templates <-> Databricks (workspace.cashcan_faces)
camera -> pi_client --classify ─┬─ face_api /match + liveness -> live session (who)
                                └─ ItemGate -> ONNX classifier -> LidController (what)
                                        -> face_api POST /interactions (X-Bin-Key): reward from face_api/app/rewards.py,
                                           row in workspace.cashcan_app.interactions: none | held | pending
                                        -> pending: claimed (-> sending) -> website POST /api/payout (shared secret):
                                           live SOL/CAD rate -> lamports -> devnet transfer, memo cashcan:<interaction_id>
                                        -> paid + tx_signature + lamports + rate   (or failed -> retried)
user saves a wallet (PUT /me)  -> held rewards -> pending -> paid, same path
Vercel cron every minute       -> face_api /cron/reconcile: retry failed (backoff), resolve stuck "sending" by memo lookup
website /dashboard             -> face_api GET /me/activity (Auth0)
city dashboard                 -> Databricks view workspace.cashcan_app.city_activity
```

### Reward table
One table, on the server (`face_api/app/rewards.py`, served at `GET /face-api/rewards`; the website's Prices page reads it):
- **Cans** (BC Return-It deposit containers): **5¢ CAD**, half the 10¢ BC deposit, paid in SOL at the live SOL/CAD rate at the moment the payout
  is sent. **Organics and waste:** 0 for now.
- Only a verified person gets a reward. Nobody identified: the lid still opens, reward 0. The bin never sends an amount.
- Unsure item (confidence below 0.75): reward 0.
- No wallet yet: the reward is **held** and paid as soon as the person adds a wallet.
- Paid on Solana **devnet** (test tokens, no cash value).

### Anti-abuse (judges will ask)
- Rate limit per user: one paying drop per 30 s, checked on the server from the interactions table.
- Minimum classifier confidence before any reward.
- A reward needs a live verified face session. The head-turn liveness check rejects a held-up photo or screen. It does **not** stop a replayed video, a 3D mask or a deepfake, and we say so openly.
- Each interaction has a bin-chosen id and is stored once; every payout step is a claim on the expected status, and the transfer carries the
  interaction id as a memo that is checked before sending, so retries and overlapping workers can't pay twice.
- The bin must send a bin key to record interactions; one face can't be enrolled to two accounts.
- Not built yet: rejecting repeated identical items, and a second camera that must agree. The item gate also can't tell a hand from an item.

---

## Repository layout

```
cashcan/
├── README.md        this file: problem, solution, status, plan
├── backend/         operator CLI for the devnet treasury (payouts run in website/app/api/payout)
├── ml/              garbage classifier (3 bins): training, results, model comparison, RKNN conversion scripts
├── face_api/        Python face recognition: API + enrollment page, matching, liveness,
│   │                SQLite and Databricks face stores, tools, measured results
│   ├── app/         FastAPI app (main.py), face_engine, matching, liveness, sessions, stores
│   ├── tools/       face_demo (enroll, identify, selftest), databricks_sync (push, pull, search),
│   │                evaluation, robustness and training experiments
│   ├── tests/
│   └── EVAL.md, ENROLLMENT.md, ROBUSTNESS.md, TRAINING.md, DATABRICKS_CHECK.md    measured results
├── pi_client/       bin controller: camera -> face match + liveness (who) and item classifier (what)
│                    -> opens the right lid -> records the interaction (Python/OpenCV; Pi, Radxa or a Mac)
├── dashboard/       Databricks AI/BI city dashboard over workspace.cashcan_app.city_activity
├── databricks/      SQL for the app tables (users, bins, interactions), migrations 002/003, views
└── website/         Next.js + GSAP site (cashcan.biz): home with the scroll story, sign-up / log-in (Auth0),
                     face enrollment, dashboard, profile + wallet, prices and info pages
```

Each folder has its own README with setup and commands.

---

## Scope and status

### Must have (MVP)
- [x] **Classifier:** 3 physical bins (organics / cans / waste), matching the hardware's 3 openings (see `ml/class_map.yaml`). MobileNetV2 trained on TrashNet, GD and RealWaste, plus our own photos to patch gaps found in live-webcam testing. 92%+ on a held-out test set. Live-tested on a webcam (`ml/scripts/live_predict.py`), not yet on the bin's cameras.
- [x] **Bin controller:** `pi_client --classify` uses one camera for both the face match and the item, opens the item's lid and records the interaction with a retry outbox. Unit-tested and tried on a laptop webcam with `--show`; lids are simulated until the hardware is chosen.
- [x] **Payout path:** the face API decides the reward and pays it at once through the website's `/api/payout` (devnet, memo per interaction), holds rewards until a wallet exists, and a cron retries failures. Tested with unit tests and against the real Databricks tables and the real route; **the on-chain transfer itself is verified only once the devnet treasury is funded** (see the PR).
- [ ] Local rule lookup table (item -> correct bin + reason)
- [ ] Real lid hardware and bin camera; tune the item region and thresholds on them
- [x] **Reward table:** one server-side table (`face_api/app/rewards.py`): 5¢ CAD per can (half the BC deposit), converted to SOL at the live rate when paid; confidence gate and per-user cooldown on the server.
- [x] **Face registration and match:** the website's enroll page and `face_api/` enroll from 1 to 3 photos behind a consent screen (mandatory before using the dashboard; a face already registered to another account is refused) and store only numeric templates, never photos (locally and in Databricks Delta + Vector Search). They also run a head-turn liveness check and offer a delete endpoint. Recognised 99.0% / 97.8% / 93.6% of enrolled people on public photos with 3 / 2 / 1 enrollment photos (0 wrong names), and 7 of 7 on a real laptop webcam with four people. **Not yet tested on the bin hardware.**
- [x] **One activity record:** `workspace.cashcan_app.interactions` holds every drop and its payout. `workspace.cashcan.activity_log` is retired (a view over interactions, `databricks/003_retire_activity_log.sql`).
- [x] **Dashboards on real data:** the website's `/dashboard` (the user's own drops and rewards) and the Databricks AI/BI city dashboard over `workspace.cashcan_app.city_activity` (`dashboard/README.md`).
- [ ] Gemini API: plain-language "why this bin" text and auto-labeling of photos

### Nice to have
- [ ] Account page with payout history
- [ ] Short in-app walkthrough

### Cut for the 24-hour build
- Real money and the $ -> SOL -> $ conversion. The demo runs on **Solana devnet** (or a local test validator) with test tokens only. The conversion is mocked in the pitch.

---

## What's left

1. **Bin sessions across server instances.** Bin sessions live in one face API instance's memory; on Vercel, `/match` and `/interactions` can reach
   different instances, and the drop is then recorded as unrecognised (no reward). A shared session store (or a signed session token) fixes it.
2. **Remaining anti-abuse checks:** reject repeated identical items, and tell a hand from an item.
3. **Real hardware:** lid actuators (`--lids lids.json` maps each bin to shell commands) and the bin camera, then tune the item region and thresholds on them.

## How to run the demo

1. **Database** (once): run `databricks/002_interactions_payouts.sql` in a SQL warehouse (`cd dashboard && python dbsql.py -f ../databricks/002_interactions_payouts.sql`).
   The owner of `workspace.cashcan` runs `databricks/003_retire_activity_log.sql`. Add each bin to `workspace.cashcan_app.bins`.
2. **Treasury:** `cd backend && npm install && npm run init-treasury`, fund the printed address with devnet SOL at https://faucet.solana.com
   (a person has to; the RPC faucet is closed), then `npm run cli -- export-secret` for the next step.
3. **Vercel env vars** (project-wide, Production and Preview): `TREASURY_SECRET_KEY`, `SOLANA_RPC_URL=https://api.devnet.solana.com`,
   `PAYOUT_URL=https://cashcan.biz/api/payout`, `PAYOUT_SECRET` and `CRON_SECRET` (two long random strings), `BIN_API_KEYS="bin-1:<key>"`, plus the
   existing `DATABRICKS_*` and `AUTH0_*`. See `face_api/.env.example` and `website/.env.example`. Redeploy.
4. **Check the money path:** `python scripts/e2e_devnet.py deployed --base-url https://cashcan.biz --bin-key <key> --session-token <live bin session>
   --auth0-token <test user's access token>` (or `local` mode against `npm run dev`; see the script's header).
5. **At the bin:** `pi_client --classify` with `CASHCAN_BIN_KEY`; drop a can; the bin shows the server's reward and status, the user's dashboard and
   the city dashboard show the drop.

---

## Tech stack (not locked)

| Area | Choice |
|---|---|
| Vision model | MobileNetV2, 3 bins (organics / cans / waste), 92%+ held-out. Compared with YOLO11n-cls (about 92-94% either way, so training data mattered more than the model). Kept MobileNetV2 because it matches the RK3582's official RKNN conversion example. RKNN script is in `ml/scripts/`, not yet verified on the board. |
| Face recognition | InsightFace `buffalo_s` (detector + MobileFaceNet/ArcFace, 512-number templates). Templates only, never photos. Weights are **non-commercial research only**, so a commercial product needs a different licence. |
| Edge device | Radxa ROCK 5C Lite (RK3582 with NPU); earlier plan was a Raspberry Pi. `pi_client/` runs on either. |
| Backend | Node/TypeScript payout (`backend/`) + Python FastAPI face service (`face_api/`) |
| Payout | Solana devnet via `@solana/web3.js`. The demo uses a local `solana-test-validator` for reliability. |
| Data | Databricks Free Edition: `workspace.cashcan_app` (accounts, bins, interactions + payouts), `workspace.cashcan_faces` (Delta + Vector Search, about 250 ms per lookup), and an AI/BI dashboard (`dashboard/`) |
| Website | Next.js 15 + GSAP (`website/`), Auth0 log-in, face enrollment through `face_api/`. Live at cashcan.biz. |
| Gemini API | "Why this bin" explanations (English / Cantonese / Mandarin) and photo auto-labeling. The local model stays the main classifier so the demo never depends on venue wifi. |
| Domain | cashcan.biz |

---

## Face recognition: where it stands

| Question | Answer (measured; limits in the reports under `face_api/`) |
|---|---|
| How it works | A face becomes a 512-number template. Matching is cosine similarity against saved templates, with a 45% threshold. No photos are stored. |
| Photos at enrollment | 1 to 3. On public photos: 93.6% / 97.8% / 99.0% recognised with 1 / 2 / 3 photos, no wrong names. One frame from the **bin's own camera** recognised 90% of later frames, against 81% for a phone or studio photo. |
| Real-world check | Laptop webcam, four people, one enrollment photo each: right person on top 7 of 7 times. Right-person scores were 58-83%, the highest wrong-person score was 19%. Small sample. |
| Distance and lighting | Copes with dim, dark, side and warm light (92-98% in simulation). Faces narrower than about 48 px are asked to move closer. |
| Liveness | Random head-turn challenge. Stops a photo or screen; not a replayed video, mask or deepfake. Not yet tried with a real head turn. |
| Not done | Running on the bin hardware, NPU conversion of the face model, self-updating templates. |

Try it on a laptop (macOS or Linux, Python 3.13/3.14; first run downloads about 125 MB). Full steps in `face_api/README.md`:

```bash
cd face_api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pip uninstall -y opencv-python opencv-python-headless && pip install opencv-python
python -m tools.face_demo enroll --name yourname --count 3
python -m tools.face_demo identify --webcam
python -m tools.face_demo selftest --outsider
```

---

## Data

- Trained on three public datasets (TrashNet, GD, RealWaste, credited with licences in `ml/README.md`), mapped onto the 3-bin scheme.
- Kept a real **held-out test set** (a slice of RealWaste never trained on) and report honest accuracy, including early failures (one iteration scored 63% before a fix; see `ml/class_map.yaml`).
- When live-webcam testing found gaps (a tall can shape, webcam lighting and clutter), we added 20-40 of our own photos targeting exactly those gaps. Before/after numbers are in `ml/class_map.yaml`.
- Local rules must be checked against the current Recycle BC and Metro Vancouver accepted-materials lists before anything is hard-coded. **Not yet verified**: `ml/rules.yaml` is all TODO on purpose.

---

## Awards we're targeting (HackCamp 2026, beginner team)

| Award | Why we fit | What we must do |
|---|---|---|
| Overall / Beginner Overall Winner | Automatic | Working demo, clear pitch |
| Best Problem-Solution Fit (beginner) | Clear problem (26.6M tonnes disposed, only 27% diverted, no incentive to recycle) and a direct fix (pay per correctly recycled item) | Opt in. Problem statement + solution description on Devpost |
| Best Hardware | Smart bin with a camera, edge board and lids that open for the right container | Opt in. Show the physical bin working |
| Community Impact | Less recyclable material in landfill, cleaner recycling streams | Opt in. Brief impact statement on Devpost |
| MLH: Best Use of Solana | Rewards paid on Solana | Opt in. Confirm with MLH mentors that devnet is acceptable |
| Sponsor: Best Use of Databricks | Activity log, app tables, sorting analytics dashboard, face-template store (Delta + Vector Search) | Opt in. Dashboard is built on demo data; show it in the demo |
| MLH: Best Use of Gemini API | Explanations and photo auto-labeling | Opt in. Gemini must do real work (not built yet) |
| MLH: Best Domain (GoDaddy Registry) | cashcan.biz. .biz is run by GoDaddy Registry, so it is likely eligible | Opt in. Confirm with MLH that .biz is on the eligible list |

**Not targeting:** Most Accessible Design and Best Design (they need a Figma file and design time we don't have).

## Submission checklist (Devpost)

- [ ] GitHub repository link
- [ ] Demo video, max 4 minutes
- [ ] Opt in to each award and read its extra requirements
- [ ] Problem statement and solution description
- [ ] Impact statement
- [ ] Hardware shown working
- [ ] Short explanations of the Databricks, Gemini and Solana usage
- [ ] Domain eligibility confirmed (if opting in)

## Pitch notes

- **Opening line:** "In 2022, Canada sent a record 26.6 million tonnes of waste to landfill and incineration. Only about a quarter of what we throw out gets recycled. What if recycling right paid you?"
- Second beat: "It says compostable. In Vancouver, it still goes in the garbage." That's why the bin uses local rules.
- Live demo: face match, hold up a can, the cans lid opens and the reward appears; then a wrapper goes to waste with no reward.
- Explain who funds it: haulers pay for clean material, and part of that becomes the users' rewards.
- Be ready to explain how this differs from deposit-refund programs for drink containers. Today CashCan rewards the same cans, but at the bin, instantly, with no trip to a depot; the plan is to reward more categories and follow local rules.
- Show real held-out accuracy, including where the model fails.
- Face recognition, honestly: 7 of 7 on a real webcam (small sample), 99% on public photos with 3 enrollment photos, 94% with 1. A photo or screen is rejected; a replayed video is not.
- "Why a face?" It ties each reward to one real person without a card or phone. Privacy: opt-in, templates only, deletable.

---

## Known risks and limits

- Prototype dataset: accuracy will drop on messy real-world items.
- Payout abuse is possible without strong rate limits and confidence thresholds.
- Crypto brings regulatory and credibility questions. We use devnet only.
- The public devnet faucet is unreliable for a live demo, so we use a local `solana-test-validator` (see `backend/README.md`).
- Facial recognition handles biometric data (consent, storage, deletion). We haven't verified what applies in BC. Keep it opt-in, templates only.
- Liveness stops photos and screens, not a replayed video, a 3D mask or a deepfake. Most published face numbers are on public photos, which are easier than a bin webcam.
- Enrollment location matters: a phone or studio photo recognised about 81% of later webcam frames, against about 90% for a frame from the bin's camera (`face_api/ENROLLMENT.md`).
- The face model weights are non-commercial research only, and both Databricks workspace users are admins who can read the stored templates.
- Local rules change. Rules here are as of build time and must be re-verified.

## Open questions

- [ ] Payout formula and which items are reward-eligible
- [x] Who funds payouts: the hauler's payment for collected material, converted to SOL
- [x] Domain: cashcan.biz (confirm GoDaddy Registry award eligibility; check trademark)
- [x] Face library: InsightFace `buffalo_s` (research-only licence)
- [x] Face match threshold: 45%
- [x] Which camera does the face match: one camera does both face and item (`pi_client --classify`)
- [x] Link website sign-up to face enrollment
- [ ] Where people enroll: at the bin (recognised more often) or with a phone photo
- [ ] Self-updating face templates (81% -> 91% on one person): build them with consent, a cap and liveness?
- [ ] Lid hardware
- [ ] Should organics earn a reward too?
- [ ] Verified local rules for the items we demo

---

## Credits

Team: TBD
