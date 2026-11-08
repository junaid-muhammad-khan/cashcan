# CashCan

**Smart sorting bins that know your city's rules, and pay you for sorting correctly.**

> Hackathon project (24 hours). Theme: solve a problem in this world.
> Status: in progress. **Built and tested on their own:** the Solana payout service (`backend/`), the garbage classifier (`ml/`), the face recognition system (`face_api/`, `pi_client/`) with its Databricks face database, and the website (`website/`). The face system is merged and has been tried on a real laptop webcam with the team. **Not done yet:** wiring the pieces together on the device (see "Wiring the pieces together"), the local rule table, the dashboard, and a hardware demo. Nothing has been run on the real bin hardware yet.

---

## Repository layout

```
cashcan/
├── README.md        this file: plan, status, layout
├── backend/         Node/TypeScript Solana payout service + Databricks activity log
├── ml/              garbage classifier (3 bins): training, results, model comparison, RKNN conversion scripts
├── face_api/        Python face recognition: API + enrollment web page, matching, liveness,
│   │                SQLite and Databricks face stores, tools, measured results
│   ├── app/         FastAPI app (main.py), face_engine, matching, liveness, sessions, stores
│   ├── tools/       face_demo (enroll, identify, selftest), databricks_sync (push, pull, search), and the
│   │                evaluation, robustness and training experiments
│   ├── tests/
│   └── EVAL.md, ENROLLMENT.md, ROBUSTNESS.md, TRAINING.md, DATABRICKS_CHECK.md    measured results
├── pi_client/       bin-side client: front camera -> /match -> liveness challenge -> session events
│                    (plain Python/OpenCV; runs on a Raspberry Pi or the Radxa board)
└── website/         Next.js + GSAP site: scroll-animated home, sign-up, log-in, account pages
                     (prototype auth; not yet linked to face_api/)
```

Each folder has its own README with setup and commands. To try the face recognition on your own laptop see "Face recognition: where it stands" below, then `face_api/README.md` for the full steps.

How the pieces are meant to connect (the arrows into the payout are **not built yet**):

```
website sign-up -> (not linked yet) -> face_api /enroll
front camera -> pi_client -> face_api /match + liveness -> live session {user, wallet}  ─┐
                                   face templates <-> Databricks (workspace.cashcan_faces) │
item camera  -> ml classifier -> item + confidence ─────────────────────────────────────┤
                                                                                         v
                                       backend payout (Solana) -> Databricks activity_log
```

---

## The problem

People sort waste wrong, and contamination ruins whole batches of recycling and compost.

- Sorting rules are local and confusing. In Metro Vancouver, an item labelled "compostable" may not be accepted in the green bin. Food-soiled paper and foodware cause confusion.
- Existing smart bins mostly classify by **material** (plastic, paper, metal, glass), not by **what your city actually accepts**.
- Image classifiers that score 95%+ on benchmarks often fail on real, contaminated items, and no public dataset of contaminated recyclables exists (per a June 2026 preprint).
- Signage and outreach reduce contamination but do not eliminate it. There is little immediate reason for a person to get it right.

## Our idea

A bin with a camera and sensor that:

1. Identifies the item and decides the correct bin **by local Metro Vancouver rules**, not just by material.
2. Detects **contamination** (for example, a greasy container).
3. Uses **two cameras (one on top, one on the front)** to look at the item from two angles, so detection is more reliable and harder to fool.
4. **Rewards** the user with a small crypto payout depending on what the item is detected as (which items earn a reward, and how much, is defined in the reward table below).
5. Logs everything to a dashboard, so we can show where and what people get wrong.

**Our edge:** local-rule-aware plus contamination-aware sorting, tied to an incentive. We searched and found no product doing exactly this. That is a search result, not proof that none exists.

---

## How it works

```
Register user
   -> Facial registration (enroll face, link it to the user's account)
   -> Connect Solana wallet
   -> At the bin: face match identifies the user
   -> Two cameras (top + front) capture the item
   -> Classifier (item + local rule + contamination)
   -> Reward table decides which items earn a payout
   -> Payout (devnet SOL)
   -> Activity log / dashboard
   -> (loops back for the next item)
```

### Reward table
The classifier detects the item, then a lookup table decides whether it earns a reward.
- Reward-eligible item, clean: payout.
- Reward-eligible item, contaminated: reduced or no payout.
- Item that earns no reward: no payout, but the bin still tells the user where it goes.
- Which items are reward-eligible and the exact amounts: **TBD** (the whiteboard note "Payout SOL by Classifier / 2" needs to be defined by the team).

### Anti-abuse (required, judges will ask)
- Rate limit per user per time window.
- Minimum classifier confidence before any payout.
- Reject repeated identical items in quick succession.
- Top and front camera detections must agree before a payout is issued.
- Face match must succeed before a payout. A head-turn liveness check (rejects a photo or screen held up) is built in `face_api/`; it does not stop a replayed video, a 3D mask or a deepfake, and that limit should be stated openly. Nothing enforces this gate at the payout yet (see "Wiring the pieces together").

---

## Scope

### Must have (MVP)
- [x] Classifier — scope changed from "12 material classes" to **3 physical bins** (organics / cans / waste, matching the hardware's 3 openings — see `ml/class_map.yaml` for why). MobileNetV2, trained on public datasets (TrashNet, GD, RealWaste) plus real photos of actual items after live-webcam testing exposed gaps. 92%+ on a held-out test set; live-tested with a webcam (`ml/scripts/live_predict.py`), not yet on the real bin hardware/cameras
- [ ] Local rule lookup table (item -> correct bin + reason)
- [ ] Two cameras (top and front) + Raspberry Pi capturing each item
- [ ] Bin indicator (LEDs or display) showing the correct bin and why
- [x] Reward table + devnet SOL payout for reward-eligible items — backend built and verified end-to-end (reward lookup, contamination multiplier, confidence gate, per-user cooldown, real signed transfer); see `backend/README.md`. Reward amounts in the table are still placeholders (see Open questions)
- [x] Facial registration and face match at the bin, so each payout goes to the right user's wallet (opt-in consent screen, store face embeddings only, never raw photos, delete on request) — merged: `face_api/` and `pi_client/` enroll from 1 to 3 photos behind a consent screen, store only the numeric templates (locally and in Databricks Delta + Vector Search), run a head-turn liveness check, and offer a delete endpoint. Measured: 99.0% / 97.8% / 93.6% of enrolled people recognised on public photos with 3 / 2 / 1 enrollment photos (0 wrong names), and 7 of 7 correct on a real laptop webcam with the owner and three friends (`face_api/EVAL.md`, `ENROLLMENT.md`). **Not yet tested on the real bin hardware or with a real head turn, and not wired to the payout**
- [x] Activity log to Databricks (Delta table). `backend/src/activityLog.ts` writes each payout decision (paid or rejected) to `workspace.cashcan.activity_log` via the Databricks SQL Statement API, wired into the payout CLI; gated on `DATABRICKS_SERVER_HOSTNAME`/`DATABRICKS_HTTP_PATH`/`DATABRICKS_TOKEN` in `.env` and never throws (a Databricks hiccup must not block a real payout). Verified end-to-end against the live workspace (Free Edition, Serverless Starter Warehouse) — a real row round-tripped. The AI/BI **dashboard** on top of this table is not yet built; do that once there's more than a couple of seed rows
- [ ] Gemini API: generate the plain-language "why" text and auto-label photos to speed up data collection

### Nice to have (only if time remains)
- [ ] Simple user account page with payout history
- [ ] Short in-app walkthrough

### Cut for the 24-hour build
- Real money and the $ -> SOL -> $ conversion loop. Demo on **Solana devnet** with free test tokens only. Mock the conversion in the pitch.

---

## Proposed tech stack (not locked)

| Area | Proposed |
|---|---|
| Face recognition | InsightFace `buffalo_s` (face detector + MobileFaceNet/ArcFace 512-number embeddings), embeddings only, never photos — see `face_api/`. The pretrained weights are **non-commercial research only**; a commercial product needs a different licence |
| Vision model | MobileNetV2 classifier into 3 bins (organics / cans / waste) — see `ml/` (92%+ on a held-out dataset). Compared against YOLO11n-cls (same ballpark, ~92-94% either way — confirms the model wasn't the bottleneck, training-data coverage was) and kept MobileNetV2 since it matches the RK3582's official RKNN conversion example. Patched twice with real photos after live-webcam testing found gaps: a tall/slim can shape the public datasets don't show, and general live-camera conditions (lighting, clutter) vs. the datasets' clean photos — both documented in `ml/class_map.yaml` with before/after numbers. RKNN conversion script is in `ml/scripts/`, not yet verified on the board |
| Edge device | Radxa ROCK 5C Lite (RK3582, NPU) per `ml/README.md`; earlier plan was a Raspberry Pi. The bin client `pi_client/` is plain Python/OpenCV and runs on either. Camera layout: see Open questions |
| Backend | Two services: Node/TypeScript payout (`backend/`) and Python face recognition API (`face_api/`) |
| Website | Next.js 15 + GSAP, see `website/` (sign-up, log-in, account; prototype auth). Its sign-up form has an opt-in face-enrollment checkbox that is not connected to `face_api/` yet |
| Face database | Databricks Delta tables + Vector Search index in `workspace.cashcan_faces` (schema separate from `workspace.cashcan`), with local matching on the device after a pull — see `face_api/README.md` |
| Payout | Solana **devnet** — see `backend/` (Node/TypeScript, `@solana/web3.js`); demoing against a local `solana-test-validator` for reliability, see `backend/README.md` |
| Dashboard | Web app, data in Databricks (Free Edition: Delta table + AI/BI dashboard). `workspace.cashcan.activity_log` table live and receiving rows via `backend/src/activityLog.ts`; the AI/BI dashboard view itself not yet built |
| Gemini API | Plain-language "why this bin" explanations (English / Cantonese / Mandarin) and auto-labeling of our photo dataset. Keep the local model as the main classifier path, so the demo never depends on venue wifi |
| Domain | cashcan.com (set). See the domain note under "Awards we're targeting" |
| Version control | Git |

---

## Wiring the pieces together (not built yet)

Each piece works alone; nothing calls the next one yet. What is missing is one small "bin controller" process on the device:

1. Read the bin client's JSON events (`session_started` carries the user's wallet, `session_ended` closes it) — `pi_client/README.md`.
2. Run the item classifier from `ml/` on the item camera and get an item class and confidence.
3. When a classification is stable **and a live face session exists**, call the payout (`backend/`: `payout --user <wallet> --item <class> --confidence <0-1>`). No live session means no payout; this is the face-match gate the payout README lists as missing.
4. Decide what `activity_log.user_id` holds. The payout currently logs the wallet address; the face system identifies people by a name. Log both or map one to the other.
5. Still missing from the anti-abuse list: rejecting repeated identical items and requiring the two cameras to agree.

## Face recognition: where it stands

| Question | Answer (all measured; limits in the reports under `face_api/`) |
|---|---|
| How does it recognise someone? | A pretrained face detector plus a MobileFaceNet model (InsightFace `buffalo_s`) turn a face into a 512-number template. Matching is cosine similarity against the saved templates, with a 45% line. No photos are stored. |
| How many photos at enrollment? | 1 to 3. On public photos, 93.6% / 97.8% / 99.0% of enrolled people are recognised with 1 / 2 / 3 photos, with no wrong names. What is saved matters more than how many: one ordinary frontal frame from the **bin's own camera** recognised 90% of later frames, against 81% for a phone or studio photo. |
| Real-world check | Laptop webcam, owner plus three friends (each enrolled from one photo): the right person came out on top 7 of 7 times, right-person scores 58-83%, highest wrong-person score 19%. Small sample. |
| Distance and lighting | The model copes with dim, dark, side and warm light (92-98% in simulation). Faces narrower than about 48 px are asked to move closer (with realistic camera noise the model alone drops to about 73% at 38 px and 42% at 28 px); the quality gates are strict for enrollment and lenient for recognising. |
| Where the vectors live | Databricks (`workspace.cashcan_faces`): a Delta table plus a Vector Search index, about 250 ms per lookup. The bin itself matches locally after pulling the templates. |
| Liveness | A random head-turn challenge. Stops a held-up photo or screen; not a replayed video, mask or deepfake. Not yet tried with a real head turn on a camera. |
| Not done | Running on the bin hardware, the NPU conversion of the face model, the bin controller below, and self-updating templates (they need consent, a cap and liveness first). |

Try it on a laptop (tested on macOS and Linux with Python 3.13 and 3.14; the first run downloads the face model, about 125 MB). Full steps, including the Databricks sync, are in `face_api/README.md`:

```bash
cd face_api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip uninstall -y opencv-python opencv-python-headless && pip install opencv-python
python -m tools.face_demo enroll --name yourname --count 3
python -m tools.face_demo identify --webcam
python -m tools.face_demo selftest --outsider
```

## Data plan (what actually happened)

The original plan below (photograph ~12 items ourselves) didn't happen — public datasets turned out
to be the faster path, with our own photos used surgically to patch specific gaps instead of as the
primary data source:

- Trained on three public datasets (TrashNet, GD, RealWaste — credited with licenses in `ml/README.md`), collapsed onto the 3-bin scheme.
- Kept a genuine **held-out test set** (a slice of RealWaste never trained on) and reported honest accuracy, including early failures (one iteration scored 63% before a fix — see `ml/class_map.yaml`'s notes).
- When live-webcam testing found specific gaps (a tall can shape, general webcam lighting/clutter conditions), took a *small* number of our own photos (20-40) targeting exactly those gaps, rather than a large from-scratch shoot — much faster, and the before/after is documented in `ml/class_map.yaml`.
- Verify rules against the current Recycle BC and Metro Vancouver accepted-materials lists before hard-coding anything. **Not yet verified** — `ml/rules.yaml` still has all values as TODO on purpose.

---

## 24-hour timeline

| Hours | Goal |
|---|---|
| 0-2 | Lock scope, pick 12 items, pull and verify local rules, assign roles |
| 2-8 | Collect and label photos, split off test set |
| 8-14 | Fine-tune model, wire to rule table, output bin + reason |
| 14-18 | Hardware demo: two cameras, Pi, bin indicators, devnet payout |
| 18-22 | Dashboard, anti-abuse checks, seeded demo flow that never depends on live luck |
| 22-24 | Rehearse the 3-minute pitch out loud, twice |

## Team roles

| Role | Owner |
|---|---|
| Hardware (two cameras, Pi, indicators) | TBD |
| Data + model + rule table | TBD |
| Backend + payout + dashboard | TBD |
| Pitch + demo script | TBD |

---

## Awards we're targeting (HackCamp 2026)

We are a **beginner team**, so the Beginner stream applies.

| Award | Why we fit | What we must do |
|---|---|---|
| Overall Winner / Beginner Overall Winner | Automatic, no opt-in | Working demo, clear pitch |
| Best Problem-Solution Fit (beginner only) | Clear problem (local sorting rules + contamination) and a direct solution | Opt in. Write a problem statement and solution description in Devpost |
| Best Hardware | Two cameras + Raspberry Pi bin | Opt in. Show the physical bin working in the demo |
| Community Impact | Cleaner recycling and compost streams for a community | Opt in. Write a brief impact statement in Devpost |
| MLH: Best Use of Solana | Reward payouts on Solana | Opt in. Solana must be a real part of the flow. Confirm with MLH mentors that devnet is acceptable |
| Sponsor: Best Use of Databricks | Activity log and contamination analytics, plus the face-template store (Delta table + Vector Search index) | Opt in. Use at least one Databricks product for real (Delta table + dashboard); the Vector Search lookups are verified, the dashboard is not built yet |
| MLH: Best Use of Gemini API | Explanations and photo auto-labeling | Opt in. Gemini must do real work in the product, not a token call |
| MLH: Best Domain (GoDaddy Registry) | Only if our domain is eligible | See the domain note below |

**Not targeting:** Most Accessible Design and Best Design (both need a Figma file and design time we don't have). Revisit only if a teammate wants to own Figma.

### Domain note (important)
- cashcan.com is a **.com**, which is run by Verisign, not GoDaddy Registry. The award requires an "eligible GoDaddy Registry domain name", so cashcan.com is **likely not eligible**.
- GoDaddy Registry operates TLDs such as .co, .us, .biz, .club, .nyc, .design and .tv. A domain like **cashcan.co** would likely qualify.
- Availability of cashcan.co (or similar) is **not checked**, and the exact eligible list should be confirmed with MLH or the GoDaddy Registry table at the event.
- Decide before the hackathon: keep cashcan.com for branding and skip this award, or register an eligible domain too. Do not claim the award with an ineligible domain.

## Submission checklist (Devpost)

- [ ] Link to GitHub repository
- [ ] Recorded demo video, max 4 minutes (optional but highly recommended)
- [ ] Figma link (only if applying for a design award)
- [ ] Opt in to each award we want, and read each award's extra requirements
- [ ] Problem statement and solution description (Best Problem-Solution Fit)
- [ ] Brief impact statement (Community Impact)
- [ ] Hardware component shown (Best Hardware)
- [ ] Databricks product used, with a short explanation
- [ ] Gemini API usage, with a short explanation
- [ ] Solana integration, with a short explanation
- [ ] Domain eligibility confirmed (if opting in)

## Pitch notes

- **Opening line:** "It says compostable. In Vancouver, it still goes in the garbage."
- Show the bin catching a contaminated item live, then the payout changing.
- Show real held-out accuracy, including where the model fails.
- Say plainly: "We found no product doing local-rule plus contamination sorting, but our dataset is small."
- **Who funds the payouts:** the recycling/hauling company that picks up the bin's contents pays CashCan cash for the collected material. CashCan converts part of that revenue into SOL to fund the treasury wallet, which pays users per reward-eligible item. See `backend/README.md` for the devnet implementation of the payout leg.
- Be ready to explain how this differs from existing deposit-refund programs for drink containers.
- Face recognition, honestly: right person 7 of 7 on a real laptop webcam (small sample), 99% on public photos with 3 enrollment photos, 94% with 1; a held-up photo or screen is rejected by the head-turn check, a replayed video is not. Quote the limits with the numbers.
- Have a one-sentence answer for "why facial recognition?" (for example: it ties each reward to one real person without carrying a card or phone) and for privacy: opt-in, embeddings only, deletable.

---

## Known risks and limits

- Small self-collected dataset: this is a prototype, not a solved problem.
- Classifier accuracy will drop on messy real-world items.
- Payout abuse is possible without strong rate limits and confidence thresholds.
- Crypto adds regulatory and credibility questions. We use devnet only.
- The public devnet faucet is unreliable for a live demo: Solana shut off its RPC auto-airdrop, and the web faucet explicitly tells AI agents/scripts not to use its form. We demo against a local `solana-test-validator` instead (unlimited SOL, no rate limit, no network dependency during judging) — see `backend/README.md` for both setups.
- Facial recognition handles biometric data, which carries privacy and legal obligations (consent, storage, deletion). We have not verified what applies in BC. Keep it opt-in, store embeddings only, and be ready to explain why a face is needed at all.
- Face matching can be fooled by a photo or screen without liveness detection, and accuracy varies across lighting and faces. Test on our own team and report real results. The head-turn liveness check in `face_api/` stops a photo or a screen showing a still, but not a video of the right person turning the right way, a 3D mask or a deepfake. Most published numbers are on public celebrity photos (LFW), which are easier than a bin webcam; the only real-webcam test so far is 7 lookups with four people.
- People will enroll with only 1 to 3 photos. A single phone or studio photo recognised about 81% of later webcam frames against about 90% for a frame from the bin's own camera, so where people enroll matters (see `face_api/ENROLLMENT.md`).
- The face recognition weights we use are for non-commercial research only (see the tech stack table), and the Databricks workspace has two users who are both admins, so both can read the stored face templates.
- Local rules change. Rules in this project are as of build time and must be re-verified.

## Open questions

- [ ] Definition of the payout formula ("Classifier / 2")
- [x] Who funds real payouts in a real deployment — the recycling/hauling company's payment for collected material, converted to SOL (see backend/README.md)
- [ ] Domain: keep cashcan.com (likely ineligible for the GoDaddy Registry award) or also register an eligible TLD such as .co. Check trademark clearance for the name either way
- [x] Which face recognition library — InsightFace `buffalo_s`, see `face_api/` (research-only licence)
- [ ] Which camera does the face match. The bin client currently reads one camera; the current idea is a dedicated face camera separate from the item camera. Confirm with whoever owns the hardware, because the anti-abuse list above assumes top and front item cameras
- [x] Face match threshold: default 45% (right-person scores 58-83% against a highest wrong-person score of 19% in the real test; 40% looks safe for single-photo enrollments but lookalikes and siblings are untested)
- [ ] Where people enroll: at the bin's own camera (recognised more often) or with a phone photo
- [ ] Self-updating templates (recognition rose from 81% to 91% on one person's frames): build them, with consent, a cap and a liveness check?
- [ ] Who builds the bin controller that joins the face session, the classifier and the payout, and what `activity_log.user_id` holds
- [ ] Link the website sign-up to the face enrollment in `face_api/`
- [ ] Camera placement and how the two views are combined (top = entry angle, front = side profile)
- [ ] Which items are reward-eligible and how much each pays
- [ ] Final list of 12 items and their verified local rules

---

## Credits

Team: TBD
