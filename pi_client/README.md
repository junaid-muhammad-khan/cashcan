# CashCan bin client (Raspberry Pi)

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
{"event": "session_ended", "user_id": "alice", "why": "expired | different_person | unrecognised_face"}
{"event": "denied", "reason": "below_threshold | ambiguous | no_enrolled_users", "score": 0.1}
{"event": "error", "message": "ConnectError: ..."}
```
A payout is allowed only while a `session_started` has no matching `session_ended`. Confirm with
`GET /session/{token}` on the API if you want the server to be the source of truth.

## How it behaves
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
