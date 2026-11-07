# CashCan face API

Face enrollment and matching for the bin. Stores 512-d ArcFace embeddings only, never photos.

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app_factory --factory --port 8000
python -m pytest -q
```

First request downloads the InsightFace `buffalo_s` model (~125 MB) to `~/.insightface`.

| Endpoint | Purpose |
|---|---|
| `POST /enroll` | form: `user_id`, `wallet`, `consent=true`, 3-8 `frames` images |
| `POST /match` | form: one `frame` image -> `{matched, user_id, score, session_token, expires_in}` |
| `GET /session/{token}` | user + wallet for a live session (payout step) |
| `DELETE /users/{user_id}` | deletes embeddings and closes sessions |

Settings are in `app/config.py` (`MATCH_THRESHOLD` 0.45, `AMBIGUITY_MARGIN` 0.05, quality gates).

## Known limits
- No liveness check yet: a photo or screen of an enrolled user can match.
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
