# CashCan face API (`face_api/`)

Python face recognition for the bin. Not to be confused with `../backend/`, which is the Node/TypeScript Solana payout service; see the root `README.md` for how the folders fit together.

Face enrollment and matching for the bin. Stores 512-d ArcFace embeddings only, never photos.

```bash
cd face_api
pip install -r requirements-dev.txt
uvicorn app.main:app_factory --factory --port 8000
python -m pytest -q
```

Open <http://localhost:8000> to enroll. The camera needs `localhost` or https (browsers block it on plain http over a LAN).

First request downloads the InsightFace `buffalo_s` model (~125 MB) to `~/.insightface`.

| Endpoint | Purpose |
|---|---|
| `GET /` | enrollment web page (consent, name + wallet, 5-frame webcam scan, delete) |
| `POST /enroll` | form: `user_id`, `wallet`, `consent=true`, 3-8 `frames` images |
| `POST /match` | form: one `frame` (+ optional `session_token`) -> with liveness on: `{matched, user_id, liveness_required, challenge_id, direction, expires_in, hint}`; with it off, or when a live session is being refreshed: `{..., session_token, expires_in}` |
| `POST /liveness/{challenge_id}/frame` | form: `frame` -> `{status: pending, hint}`, `{status: failed, reason}` or `{status: passed, user_id, session_token, expires_in}` |
| `GET /session/{token}` | user + wallet for a live session (payout step) |
| `DELETE /users/{user_id}` | deletes embeddings and closes sessions |

Settings are in `app/config.py` (`MATCH_THRESHOLD` 0.45, `AMBIGUITY_MARGIN` 0.05, quality gates).

## What recognises a face (the models)
Only two small neural networks decide who someone is. Both come pretrained from InsightFace's `buffalo_s` pack (we never trained
them; file sizes and parameter counts read from the model files):

| Step | What | Size |
|---|---|---|
| 1. Find the face | `det_500m`: a lightweight face detector (SCRFD-style) that also returns 5 landmarks (eyes, nose, mouth corners) | 2.5 MB, 0.63 M parameters |
| 2. Align | plain geometry: rotate/scale the face to a standard 112x112 crop using the landmarks | no network |
| 3. Turn the face into numbers | `w600k_mbf`: MobileFaceNet trained with an ArcFace-style loss (InsightFace's WebFace600K data) -> a 512-number template | 13.6 MB, 3.40 M parameters |
| 4. Compare | **no network**: cosine similarity (a dot product) against the stored templates, then the 45% threshold and the 5-point ambiguity rule | maths |
| Liveness | **no network**: the nose's sideways offset from the eyes, from the 5 landmarks | geometry |
| Blur / size check | **no network**: Laplacian variance of the 112x112 face, and the face size | classic image processing |

The pack also contains three more networks (3D landmarks/pose 35.9 M parameters, 106 landmarks, gender/age) that are loaded in the
default mode but not used for any decision. The garbage classifier in `ml/` is a separate model (MobileNetV2).
The pretrained weights are non-commercial research only.

## Liveness (head-turn challenge)
After a face is recognised, `/match` returns a random challenge ("turn your head to your left/right") instead of a
session. The bin streams frames to `/liveness/{id}/frame`; only a pass returns the session token that payouts need.

- **Measure:** the nose's sideways offset from the eye midpoint divided by eye distance (`turn_ratio`). On a real head
  the nose sticks out, so a turn changes it a lot; on a flat photo, even tilted, it barely moves (unit-tested with a
  3D model vs a flat one). On 6 real faces it tracked InsightFace's own yaw estimate (about -0.3 at -36 degrees).
- **Pass:** a frame facing the camera first (|ratio| <= 0.12), then a turn of >= 0.25 (~30 degrees) the asked way,
  within 10 s, every frame still matching the claimed person (>= 0.35 similarity, 3 strikes).
- **Refresh:** the same person can refresh a live session with its token for 120 s after the last proof, so nobody
  is asked to turn their head for every item. Refreshing never extends that 120 s.
- **Settings:** `CASHCAN_LIVENESS=off` disables it; `LIVENESS_TTL_SECONDS`, `LIVENESS_VALID_SECONDS`,
  `LIVENESS_ID_THRESHOLD` and the pose thresholds are in `app/config.py`.
- The camera image is assumed **not mirrored** ("left" = the user's own left). Mirrored cameras flip the direction.

## Try it on your Mac (save your face, then test it)

```bash
git clone https://github.com/junaid-muhammad-khan/cashcan.git   # skip if you already have it; check `git remote -v` says cashcan
cd cashcan && git checkout integration/face-system-and-payout
cd face_api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
# the camera preview needs the windowed OpenCV. The two OpenCV packages share the same files, so remove BOTH and
# install one (uninstalling only the headless one leaves cv2 broken):
pip uninstall -y opencv-python opencv-python-headless && pip install opencv-python
python -c "import cv2; print(cv2.__version__)"   # must print a version
```
If `pip install insightface` fails while building, run `xcode-select --install` and retry. The first run downloads the
face model (~125 MB). When macOS asks, allow the camera for your terminal. If camera 0 is your phone, add `--camera 1`.

```bash
python -m tools.face_demo enroll --name junaid                      # follow the prompts, 5 frames
python -m tools.face_demo identify --webcam                         # live: green box + name when it is you; q quits
python -m tools.face_demo identify --image ~/pics/*.jpg --annotate out/   # who is in these pictures? (saves marked-up copies)
python -m tools.face_demo evaluate --name junaid --mine ~/test/me --others ~/test/others
python -m tools.face_demo list
python -m tools.face_demo delete --name junaid
```
**Make the scores higher (add webcam templates).** Templates from a single studio photo match live webcam frames at only about
50-65% (measured on a real MacBook webcam: median 55%, max 66%, against the 45% line), while variants of the same photo match at 99%.
Add real webcam frames to the **same person**:
`python -m tools.face_demo enroll --name junaid --add --guided` (8 short steps: straight, left, right, chin up, **close, far, dim light,
side light**, so your templates cover the distances and lighting you will really stand in; plain `--add` without `--guided` only varies head pose), then
`python -m tools.databricks_sync push --name junaid --replace`. Do not enroll the same person under a second name: two similar
names are rejected as "ambiguous" (verified: a 0.90 match is refused when the same person exists under two names).
`--replace` swaps the person's templates in Databricks and keeps a real wallet that is already stored there.
A person can hold up to 40 templates (`--max-templates`); `--add` checks there is room before it captures anything, so a refused add never wastes a session.

**Steadier decisions (on by default in live mode):** the main face is judged on the average of its last 5 good frames (`--smooth 5`;
`--smooth 1` turns it off). One bad frame (blink, motion, a light flicker) no longer flips the answer, and the average is cleared the moment the
face disappears or a different-looking face steps in, so nobody can borrow another person's average. The label shows `(avg of N)`.

**Test everyone in one go:** `python -m tools.face_demo selftest --outsider` (add `--rounds 2` to go through everyone twice, `--databricks` to look people up with Databricks
Vector Search, `--names junaid,person-1` to test only some). Each person steps up when prompted, is looked up from a few averaged camera frames, and is marked PASS or FAIL against who was meant to
be there; `--outsider` adds a step for someone who is not enrolled, who should come back unrecognised. It ends with a result block you can paste and exits with code 2 if anything failed.

**If nothing seems to happen:** the terminal now prints each stage (model loading, camera opened, frames arriving) and ends with
`Stopped: <reason>`. The video window can open behind other windows; if you cannot find it, press Ctrl+C and run
`python -m tools.face_demo identify --webcam --no-window --debug`, which prints everything as text. The line
`tform.estimate(lmk, dst)` seen in older versions was a harmless library warning, now silenced.

**If it says "skipped":** the face was found but a quality gate rejected the frame, and the label says which one and by how much,
e.g. `too small: face 40px < 48px (move closer)`. Add `--debug` to see every number (face size, detector confidence, sharpness, head
turn, and your match score as a percentage with the percentage needed to match). Fixes: more light on your face, face the camera, move
closer (face at least 48 px wide), hold still, clean the lens. The percentage is a similarity score, not a probability of being right;
the default match line is 45% (`--threshold 0.50` is stricter; with your own frontal scores of 56-82% and strangers topping out at 25%, 50% is a sensible choice once a friend has also been tested). To experiment, override a gate for one run: `python -m tools.face_demo --min-face 45 identify --webcam --debug`
(also `--min-sharpness`, `--min-det`).

**Two tiers of quality gates.** *Enrollment is strict* (face >= 80 px, detector >= 0.60, sharpness >= 60), because a bad frame would be saved
as a bad template. *Identification is lenient* (face >= 48 px, detector >= 0.45, sharpness >= 25), because a weak frame can only fail to
match: the match threshold, not these gates, keeps strangers out. Measured on LFW, letting in the 27 photos the strict gates rejected gave
93% recognised and 0 wrong names, and strangers accepted did not change. Both the API (`/enroll` strict, `/match` lenient) and the tools use
the split. In `ROBUSTNESS.md`, the old gates rejected 45% of warm-lamp photos and 99% of small faces that the model alone recognised 96-97% of the time; with the lenient tier, warm-lamp photos went from 52% to 96% recognised at the bin and side light from 75% to 96%.

**Sharpness is measured at a fixed size and contrast.** The face is resized to 112x112 and its contrast standardised before the blur
measure, because the raw crop confused two things with blur: a close face (the same sharp photo scored 1067 at a 100 px face and 27 at
453 px) and dim light (the same photo scored 34 to 530 depending on lighting, and about 300-430 after the fix). Genuine blur still
reads low (a sigma-4 blur drops it from 395 to 33).

`evaluate` is the accuracy test: put photos of you in one folder (different light, angles, glasses, a different day)
and photos of other people in another. It lists every photo as ok/ERR, your lowest score vs the others' highest, and
whether a clean threshold exists. The more varied photos, the more it tells you.

Your face is saved as 512 numbers (no photo) in `face_api/cashcan_faces.db` (git-ignored), the same database the API and
enrollment page use; `delete` removes it. This is local only for now. Databricks Vector Search is the next step once
there is a workspace to point at. Not yet run on macOS itself (developed and tested on Linux, with video files
standing in for a camera).

## Databricks (face templates + Vector Search)
Workspace `dbc-38b8f0fd-7cd5.cloud.databricks.com`, schema `workspace.cashcan_faces` (separate from Trevor's `workspace.cashcan`):
`users` (wallet, consent time) and `face_templates` (512-d templates, Change Data Feed on), plus Vector Search endpoint
`cashcan-faces` (standard; storage-optimised is not supported on this workspace) with Delta Sync index `face_templates_index`.
Code: `app/databricks_store.py`, CLI: `python -m tools.databricks_sync` (see its docstring). Needs `DATABRICKS_HOST`,
To swap someone's old photo for a new one without losing their wallet or consent record, `DatabricksFaces.replace_templates` writes the new template first and deletes the old
ones second (so nobody is ever left with none) and can keep chosen old templates; after a change in Databricks run `python -m tools.databricks_sync pull --refresh` on each machine so its
local copy matches. Delta keeps the table history, so a mistaken change can be undone with `RESTORE TABLE ... TO VERSION AS OF <n>`.
Try the Vector Search lookup with one command and no files: `python -m tools.databricks_sync search --webcam` takes a photo from your camera and
prints the closest people with a similarity percentage (use `--image <real JPG or PNG path>` for a file; HEIC is not supported).
`DATABRICKS_TOKEN` (your personal access token, never committed) and `DATABRICKS_WAREHOUSE_ID=9a5194b5eb7321ed`.

Checked live with synthetic (random) templates, no real faces: Vector Search cosine matched the local cosine to 0.00005 and
put the right person first 5/5; push, pull (exact round trip) and delete worked; test rows were removed afterwards.
- **100-photo check** ([`DATABRICKS_CHECK.md`](DATABRICKS_CHECK.md), `python -m tools.databricks_check`): 30 enrolled + 70 strangers,
  all different people. Local and Vector Search agreed on 100/100; 29/30 enrolled recognised (the miss scored 0.37, below 0.45),
  0 wrong names, 0/70 strangers accepted; Vector Search query ~250 ms; index caught up 123 s after a bulk push.
- **Matching stays local** after `pull`. A Vector Search lookup takes a couple of seconds and a new person only appears ~2 min
  after a push (TRIGGERED sync); deletes leave the table at once but the index drops them only after its next sync.
- **Cost:** the standard endpoint bills while it exists. Delete it when you are not using it.
- **Who can read the face tables:** no grants beyond the owner exist, but Trevor Lau is also a workspace admin, and admins can read
  everything. Treat the tables as readable by both of you. Biometric data: consent, deletion on request, no photos stored.

## Enrolling with only 1 to 3 photos
Users will take 1 photo, or 3 at most. `/enroll` and the web page accept 1-3 photos (the page takes 3 quick pictures). On LFW, recognition at the 45% line is
93.6% with 1 photo, 97.8% with 2 and 99.0% with 3, with no wrong names. What is saved matters more than how many: one ordinary frontal frame from the **bin's own camera**
recognised 90% of a person's later webcam frames, against 81% for a studio or phone photo, and extra copies or variants of one photo add nothing. Details, the
threshold table and the self-updating-template idea (not built) are in [`ENROLLMENT.md`](ENROLLMENT.md). A real webcam test with the owner and three friends
(each enrolled from one phone photo) returned the right person 7 of 7 times: right-person scores 58-83%, highest wrong-person score 19%.

## Measured accuracy (LFW, latest re-run 2026-11-08 with the two-tier gates)
Full tables in [`EVAL.md`](EVAL.md); regenerate with `python -m tools.eval_lfw --data <dir>` (see its docstring).
Real pipeline, threshold 0.45, 150 enrolled people (3 photos each), 757 later photos of them, 831 photos of 600 strangers:

| What | Result |
|---|---|
| Enrolled person recognised | **99.0%** (8 of 777 not recognised) |
| Wrong person named | **0 of 777** |
| Strangers accepted | 1 of 858 at 0.45; on inspection that photo shows an enrolled person (Jimmy Carter) next to the labelled one, so it is a labelling artefact, i.e. 0 real false accepts (95% upper bound still ~0.7%) |
| Photos rejected by quality gates | enrollment tier (strict): ~4% (blur 2.5%, too small 1.7-2.0%); identification tier (lenient): 0% on LFW |
| 1:1 verification (2,199 pairs) | AUC 0.994, EER 1.18%, 99.36% accuracy at the best threshold; 95.0% at 0.45, because single-photo-vs-single-photo is stricter than matching against 3 enrolled photos |
| Liveness turn measure vs InsightFace yaw (4,400 faces) | correlation 0.93; faces within 10 degrees of frontal pass "facing camera" 95-100% and "turned" 0%; faces 30+ degrees pass "turned" 98-100%, 20-30 degrees only 47% |

Distance and lighting (simulated degradations, which fixes help and which gates were wrongly rejecting people): [`ROBUSTNESS.md`](ROBUSTNESS.md). This is celebrity press photos, a gallery of 150, and no spoof attempts. It says the model is sound, not that the bin
will hit these numbers under venue lighting. Fairness across groups was not measured. Measure on the team with `tools.tune`.

## Training experiments (LFW)
`tools.lfw_embed` embeds all 13,233 LFW images once (resumable); `tools.train_adapter` tests whether a small trained layer on
top of the frozen model beats the pretrained model on people it never saw (5 people-disjoint splits). Result in
[`TRAINING.md`](TRAINING.md): **no gain** (it overfits the training people), so nothing was adopted and the pipeline is unchanged.
```bash
pip install -r requirements-train.txt
python -m tools.lfw_embed --data <dir with data.parquet> --out <dir>/emb
python -m tools.train_adapter --emb <dir>/emb --report TRAINING.md
```
`InsightFaceEngine(modules=["detection", "recognition"])` skips the 144 MB pose model: identical embeddings (cosine 1.000000
checked on 6 faces), about 6x faster on this CPU box (46 vs 7.4 img/s). Production still loads the full pack; only the
`yaw` diagnostic needs the pose model.

## Known limits
- Anyone who knows a user name can delete that registration (no auth yet). Fine for a demo, fix before real use.
- Liveness stops a photo or a screen showing a still. It does **not** stop a video of the right person turning the
  right way, a 3D mask or a deepfake, and a failed challenge can be retried straight away (no lockout yet).
  Enrollment itself has no liveness: someone could enroll from a photo.
- Verified against real faces and the real model, but **no real head turn was tested end to end**: this environment
  has no camera. The pass path is covered by tests that fake the engine's output. Test with real people at the bin
  and tune `LIVENESS_TURN_MIN` / `LIVENESS_CENTER_MAX`.
- Threshold is untuned on our team's faces. A smoke test on a stock photo gave <=0.19 between different people and 0.98 for the same face with a brightness change.
- Sessions are in memory and lost on restart. The API has no auth, so run it on a trusted network only.

## Tuning the threshold on real faces

Run on a machine with a webcam, at least 3 people. Saves embeddings only (`tuning_data/`, git-ignored).

```bash
python -m tools.tune capture --person alice --tag enroll --count 5
python -m tools.tune capture --person alice --tag dim --count 10
python -m tools.tune capture --person alice --tag glasses --count 10
python -m tools.tune report
```

Tag `enroll` is the gallery; every other tag is a probe condition (try dim, bright, angle, glasses, mask-down, a different day).
`report` prints genuine vs impostor scores, a threshold sweep (FRR, wrong-user rate, open-set FAR) and a suggested
`MATCH_THRESHOLD`. Set it with the env var, e.g. `MATCH_THRESHOLD=0.5 uvicorn ...`. No webcam? `tools.tune ingest --person X --tag T --dir photos/`.

## Storage: Databricks (default when configured)
The API stores templates in Databricks (`workspace.cashcan_faces`) whenever `DATABRICKS_HOST`, `DATABRICKS_TOKEN` and `DATABRICKS_WAREHOUSE_ID`
are set (or `CASHCAN_STORE=databricks`). Without them it falls back to the local SQLite file (`CASHCAN_STORE=sqlite` forces that). Matching still
runs in the API process on a copy of the templates cached for 30 s and refreshed after every enroll/delete; the Vector Search index is not synced
per request (run `python -m tools.databricks_sync status`). On Vercel, set the three variables in the project settings; the SQLite file is not persistent there.

## Accounts, bins, interactions and payouts (Databricks + Auth0)
Tables: `../databricks/app_schema.sql`, then `../databricks/002_interactions_payouts.sql` (schema `workspace.cashcan_app`: `users`, `bins`,
`interactions`, `game_scores` (created on first use; `../databricks/004_game_scores.sql`), views `leaderboard` and `city_activity`). Delta does not enforce unique keys, so the code does: users are created with `MERGE` on
`auth0_sub`, interactions with `MERGE` on `interaction_id`, and every payout status change is a `MERGE ... WHEN MATCHED AND payout_status = '<expected>'`
(`app/ledger.py`), so two workers can never both pay a row.

| Endpoint | Auth | What |
|---|---|---|
| `GET/PUT /me` | Auth0 access token | profile (created on first login); pseudonym and Solana wallet. Saving a wallet pays the user's **held** rewards and returns `held_queued` / `held_paid` |
| `GET /me/activity?range=today\|week\|30d&tz=` | Auth0 access token | the user's drops: totals (items, paid SOL, paid CAD at each row's stored rate, held, pending), counts by bin, a time series and the 10 most recent drops |
| `GET /game/leaderboard?period=week\|all&limit=` | none (optional Auth0 token marks your own row) | Sort It! leaderboard: each player's best game, nicknames only, plus your own best and rank |
| `POST /game/scores` | Auth0 access token | save a finished game. The browser sends what happened (`correct`, `wrong`, `spilled`, `best_streak`, `duration_ms`, `game_id`); the server checks it is possible and works out the score (`correct x 10 + best_streak x 5`) itself. Idempotent on `game_id`; one score per 15 s per player |
| `PUT /game/nickname` | Auth0 access token | the leaderboard name (2-16 letters/numbers, no contact details), stored as the profile `pseudonym` |
| `POST /enroll` | Auth0 access token | with Auth0 on, user and wallet come from the token and profile, never the form |
| `GET /rewards` | none | the reward table (`app/rewards.py`): cents per item class |
| `POST /interactions` | `X-Bin-Key` | one sorted item; the server decides the reward and pays it (below); `interaction_id` makes retries safe |
| `GET /cron/reconcile` | `Bearer $CRON_SECRET` | Vercel cron, every minute: retries failed payouts and resolves stuck ones |
| `GET /leaderboard` | none | pseudonym and SOL earned, from paid interactions only |

### Rewards and payouts
- **Reward table** (`app/rewards.py`, the one source of truth): a can earns **5¢ CAD**, half the 10¢ BC deposit; organics and waste 0. The website's
  `/prices` page reads `GET /rewards`; `tests/test_payouts.py` fails if `website/lib/prices.ts` (its fallback) disagrees.
- **`POST /interactions`** ignores any amount the bin sends. A reward is owed only with a live verified session (`session_token`), `confidence >=
  MIN_CONFIDENCE` (0.75) and a paying class, and not within `PAYOUT_COOLDOWN_SECONDS` (30) of the same user's last paying drop (checked in the
  interactions table). Otherwise `reward_cents = 0`, status `none`, and `reason` says why (`not_recognised`, `low_confidence`,
  `not_reward_eligible`, `cooldown`).
- **Status:** `none` (no reward) · `held` (reward, no wallet yet) · `pending` (reward + wallet) · `sending` (claimed by one worker) · `paid` · `failed`.
- **Instant payout:** a `pending` row is claimed (`pending -> sending`) and sent to the website's `POST /api/payout` (`PAYOUT_URL`, `Bearer
  PAYOUT_SECRET`, `PAYOUT_TIMEOUT_SECONDS` 8) within the request. That route converts cents to lamports at the live SOL/CAD rate and sends the devnet
  transfer with memo `cashcan:<interaction_id>`; the row stores `lamports`, `cad_per_sol`, `rate_source`, `tx_signature`. A timeout leaves it
  `sending`. A paying drop takes about 10 s end to end (about 5 Databricks statements plus the transfer), so the bin waits up to 25 s.
- **Held rewards:** saving a wallet (`PUT /me`) moves the user's `held` rows to `pending` and pays them one by one (15 s budget; the cron pays the rest).
- **Reconcile** (`GET /cron/reconcile`): `failed` rows are retried with backoff (30 s, 60 s, 120 s, ...) up to `PAYOUT_MAX_ATTEMPTS` (5) sends;
  `sending` rows older than `PAYOUT_STUCK_SECONDS` (180) are looked up on chain by memo (`GET /api/payout?interaction_id=`) and become `paid` if found,
  otherwise `pending` again. The payout route itself also checks the memo before sending, so a lost response is never paid twice. 180 s is above the
  route's 30 s limit plus a blockhash's ~90 s life, so a transaction still unknown by then can no longer land.

Settings: see `.env.example` (`AUTH0_*`, `BIN_API_KEYS`, `DATABRICKS_*`, `PAYOUT_URL`, `PAYOUT_SECRET`, `MIN_CONFIDENCE`, `PAYOUT_COOLDOWN_SECONDS`,
`CRON_SECRET`, retry tuning). Tested with an in-memory ledger (`tests/test_payouts.py`) and against the real Databricks tables (`../scripts/e2e_devnet.py local`).

**Bin sessions are signed tokens** (`app/sessions.py`): `s1.<payload>.<HMAC-SHA256>` with the user, expiry, liveness time, issue time and a
random id, signed with `SESSION_SECRET`. Any instance with the same secret verifies them, so `/match`, `/liveness/.../frame` and `/interactions`
may land on different Vercel instances. Each interaction stores the random id, never the token. Revoking a user's sessions (face deleted or replaced)
only takes effect on the instance that handled it; elsewhere their token lasts until it expires (`SESSION_TTL_SECONDS`, 60 s).
Liveness *challenges* are still held in one instance's memory, so a challenge started on one instance and answered on another fails as
`unknown_or_expired` and the bin starts a new one.

## For bins that identify people on the device
`GET /gallery` (X-Bin-Key) returns every person's face templates (float16, base64) with an `ETag` version; `If-None-Match` gets a 304 when nothing changed. `POST /interactions`
accepts a `user_id` from a bin (the bin key vouches for it; unknown ids are ignored). See `../pi_client/README.md` (`--local-identity`) and `../ml/QUANTIZATION.md` for the measurements.
