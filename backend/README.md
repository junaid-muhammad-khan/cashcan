# CashCan face API

Face enrollment and matching for the bin. Stores 512-d ArcFace embeddings only, never photos.

```bash
cd backend
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
