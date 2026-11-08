# CashCan bin client (`pi_client/`, Raspberry Pi or Radxa)

Watches the **front camera**, asks the face API who is at the bin, and keeps a short session so the
payout step knows whose wallet to pay. It does not classify items or pay anyone; it only answers "who is here".

```bash
cd pi_client
pip install -r requirements.txt          # on the Pi: sudo apt install python3-opencv python3-httpx also works
python -m cashcan_pi --server http://<laptop-ip>:8000
python -m pytest -q
```

Options: `--camera` (index, `/dev/videoN`, or a video file that loops, for testing), `--send-interval`,
`--recheck-interval`, `--led-pins GREEN,RED,AMBER` (BCM numbers, needs `gpiozero`).

## Output for the payout process
JSON lines on **stdout**; human status on stderr.

```json
{"event": "session_started", "user_id": "alice", "wallet": "9xQe...", "token": "...", "expires_in": 60, "score": 0.98}
{"event": "challenge_started", "user_id": "alice", "direction": "left"}
{"event": "session_ended", "user_id": "alice", "why": "expired | different_person | unrecognised_face"}
{"event": "denied", "reason": "below_threshold | ambiguous | no_enrolled_users | liveness_expired | liveness_different_person", "score": 0.1}
{"event": "error", "message": "ConnectError: ..."}
```
A payout is allowed only while a `session_started` has no matching `session_ended`. Confirm with
`GET /session/{token}` on the API if you want the server to be the source of truth.

## How it behaves
- **Liveness:** when the server asks for a head turn, the bin shows the prompt (console or amber LED), streams frames
  every 0.25 s to the challenge, and opens the session only when the server says it passed. `session_started`
  therefore means *recognised and live*. If a live session's proof gets too old the client emits `session_ended`
  (`why: liveness_required`) and asks again.
- A cheap local Haar detector decides when to upload (every 0.7 s with a face in view). It is frontal-only and can
  miss real faces, so it **fails open**: with nothing detected it still sends one probe frame every 3 s.
  On OpenCV 5 the detector does not exist, so every frame goes out at the send interval (works, uses a bit more bandwidth).
- While a session is open it re-checks every 5 s. A different person ends it at once; two unrecognised checks in a
  row end it; one blurry frame does not.
- Server down or unreachable: LED/console shows `error`, it backs off 3 s and keeps running.
- Camera unreadable 20 times in a row: it reopens the camera.

## Not verified yet
Tested with unit tests and end to end against the real API using video files as the camera (real face model,
real matching). **Not tested on a real Pi, a real webcam, or LEDs.** CSI ribbon cameras on newer Pi OS need the
libcamera/V4L2 compatibility layer (or a `picamera2` capture swap) to appear as an OpenCV camera; USB webcams
should work with `--camera 0`. Frames travel over plain http on your network and the API has no auth: demo network only.

## Full bin controller: identity + object classifier on one camera (`--classify`)
```bash
python -m cashcan_pi --camera 0 --server https://www.cashcan.biz/face-api --classify --bin-key "$CASHCAN_BIN_KEY" \
  --item-roi 0.15,0.40,0.85,1.0 --lids lids.json     # omit --lids to simulate the lids on stderr
```
One camera frame feeds two jobs. **Who:** the existing loop (face match + head-turn check) keeps a live session = a logged-in, verified person.
**What:** `ItemGate` notices an item held still in the region of interest, `OnnxClassifier` (ml/models/mobilenetv2_cashcan.onnx, same preprocessing as
training) averages 3 looks into organics / cans / waste, and `LidController` opens that one lid.

| Situation | Lid | Record sent to `POST /interactions` |
|---|---|---|
| Verified person, confident item | the item's lid | session token + reward (cans/organics) |
| Nobody identified (or session expired) | the item's lid | no user, reward 0 |
| Unsure item (confidence below `--min-confidence`) | **waste** | reward 0 |
| Waste item | waste | reward 0 (waste never pays) |

Records carry a bin-chosen `interaction_id`; if the server is unreachable they wait in a short-lived outbox (10 min TTL, no face data) and retry with the same id, so
the server stores each once and pays it at most once. The bin sends **no reward amount**: the face API decides it (`face_api/app/rewards.py`: 5¢ CAD per
can, paid in devnet SOL at the live rate; organics and waste 0) and pays it within the request. Its answer (`reward_cents`, `payout_status` none / held /
pending / sending / paid / failed, `reason`) is in the `interaction_recorded` event and on the `--show` preview. The server also applies its own confidence
floor (`MIN_CONFIDENCE`, default 0.75) and a per-user cooldown, so a bin `--min-confidence` below 0.75 still sorts but does not pay.
`lids.json` maps each bin to shell commands, e.g. `{"cans": {"open": "servo 5 90", "close": "servo 5 0"}}`; the lid hardware is not decided yet.

Not built / not verified: the real lid hardware, tuning the item region and thresholds on the real camera
and light, and accuracy of the classifier on a bin camera (its 94% is on held-out RealWaste photos). The item gate cannot tell a hand from an item; held-still foreground is
what counts, and the classifier's confidence threshold is the second line of defence.

## Try the whole bin on a Mac with the webcam (`--show`)
```bash
git pull && cd pi_client
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip uninstall -y opencv-python-headless && pip install "opencv-python<5"      # the window needs the GUI build; <5 keeps the face pre-check
python -m cashcan_pi --camera 0 --classify --show --server https://www.cashcan.biz/face-api --bin-key "$CASHCAN_BIN_KEY"
```
A window shows your camera with: who is verified (top left; it asks you to turn your head after it recognises you), the item region (amber when something is held
still in it), the last decision (bin, confidence, reward, who gets it) and the three lids with the open one lit. `q` quits. Events print to the terminal as JSON lines.
- Sit in front of the camera first: it matches the face you enrolled on the website. Then hold a can, a banana peel or a wrapper still inside the box.
- Without a bin key the lids and decisions still work; the records are refused by the server (an `interaction_rejected` event) and nothing is paid.
- `--camera 1` if macOS picks your iPhone as camera 0. Allow camera access for the terminal when macOS asks.

Lag and "it does not see my face": server calls (0.5-4 s each, longer on a cold start) run on their own thread now, so the window stays smooth. The line above the lids shows
`local face check` (does the cheap on-device detector see a face) and `server:` (its last answer, e.g. `below_threshold 31%`, `ambiguous`, `matched 76%`). If the local check says
`no face`, run with `--no-face-precheck` to send every frame. At start-up the bin calls `/warm` so the server is awake before the first match.

## Fast identity on the device (`--local-identity`)
```bash
python -m cashcan_pi --camera 0 --classify --show --local-identity --server https://www.cashcan.biz/face-api --bin-key "$CASHCAN_BIN_KEY"
```
Without it, every frame goes to the face server (0.5 to 4 s each). With it the bin downloads the face gallery once (bin key required; refreshed every 60 s, resent only when it changed,
cached on disk so a restart or a dropped network still works) and identifies people itself: detection, embedding, matching, head-turn challenge and sessions run locally, using the
server's own code from `../face_api`, so the rules are identical. A full identification measured **~17 ms** (median) instead of seconds, and the last 3 good frames are averaged
(with a reset if a different person steps in). Records to `POST /interactions` then name the user (`user_id`), which the server accepts only from a bin with a valid key.
**Trust:** the bin holds everyone's face templates and vouches for who it saw, so protect its key and its disk. The classifier defaults to the INT8 model (see `../ml/QUANTIZATION.md`).

**Head turn: enrollment only (default).** You turn your head once when you set up face match on the website; that is how the saved face vectors are made. At the bin a recognised face
is verified from the match alone: the live frame is compared with every stored vector and the highest similarity decides (threshold 45%, and the best person must lead the runner-up by 5 points).
Add `--liveness` to ask for one random head turn at the bin as well; that stops a still photo held up to the camera, but not a video. Without it, a photo or video of a person could also be recognised.

`--save-items DIR` keeps a photo of every item the classifier looks at, named `<time>_<bin>_<confidence>[_unsure]_<id>.jpg`. Hold a few of each kind of item, then sort the photos into
`cans/`, `organics/` and `waste/` folders by what the item REALLY was. Those are training photos from this very camera (the model was trained on public photo sets, not on a bin camera).

**What the gate and crop do (tuned from a real test where cans and bottles were called waste):** the gate fires when the biggest changed blob in the box covers at least ~1.2% of it (a held can or bottle is a small blob; the old 10% threshold
meant it often never noticed them), ignores a person who fills most of the box, and the classifier is given a square crop tightly around the item, not the whole box. In a simulation (held-out can, bottle and waste photos pasted at webcam size on a plain desk),
judging the whole box got 23% of cans and bottles right; the tight crop got about 62-68%; the same photos with no scene around them get 97%. The remaining gap is the difference between public photo sets and a webcam picture:
**photos from your own camera (`--save-items`) are the way to close it.**
