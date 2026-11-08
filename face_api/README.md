# CashCan face API (`face_api/`)

Python face recognition for the bin. Not to be confused with `../backend/`, which is the Node/TypeScript Solana payout service; see the root `README.md` for how the folders fit together.

Face enrollment and matching for the bin. Stores 512-d ArcFace embeddings only, never photos.

```bash
cd face_api
pip install -r requirements.txt
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
pip install -r requirements.txt
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
**If it says "skipped":** the face was found but a quality gate rejected the frame, and the label says which one and by how much,
e.g. `blurry: sharpness 23 < 40`. Add `--debug` to see every number (face size, detector confidence, sharpness, head turn, and
your match score as a percentage with the percentage needed to match). Fixes: more light on your face, face the camera,
move closer (face wider than 80 px), hold still, clean the lens. If your webcam is just soft, relax a gate for the test:
`python -m tools.face_demo --min-sharpness 15 identify --webcam --debug` (also `--min-face`, `--min-det`). The percentage is
a similarity score, not a probability of being right; 45% is the line.

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

## Measured accuracy (LFW, 2026-11-07)
Full tables in [`EVAL.md`](EVAL.md); regenerate with `python -m tools.eval_lfw --data <dir>` (see its docstring).
Real pipeline, threshold 0.45, 150 enrolled people (3 photos each), 757 later photos of them, 831 photos of 600 strangers:

| What | Result |
|---|---|
| Enrolled person recognised | **99.2%** (6 of 757 not recognised, all scored 0.24-0.44) |
| Wrong person named | **0 of 757** |
| Strangers accepted | 1 of 831 at 0.45; on inspection that photo shows an enrolled person (Jimmy Carter) next to the labelled one, so it is a labelling artefact, i.e. 0 real false accepts (95% upper bound still ~0.7%) |
| Photos rejected by quality gates | ~3% (mostly face too small, then blur) |
| 1:1 verification (2,057 pairs) | AUC 0.997, EER 0.88%, 99.56% accuracy at the best threshold; 95.3% at 0.45, because single-photo-vs-single-photo is stricter than matching against 3 enrolled photos |
| Liveness turn measure vs InsightFace yaw (4,400 faces) | correlation 0.93; faces within 10 degrees of frontal pass "facing camera" 95-100% and "turned" 0%; faces 30+ degrees pass "turned" 98-100%, 20-30 degrees only 47% |

This is celebrity press photos, a gallery of 150, and no spoof attempts. It says the model is sound, not that the bin
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
