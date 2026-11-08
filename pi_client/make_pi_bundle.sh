#!/usr/bin/env bash
# Pack everything the bin needs into ONE small archive you can copy to the Raspberry Pi / Radxa board.
#   cd pi_client && ./make_pi_bundle.sh            -> ~/Desktop/cashcan_pi_bundle.tar.gz (about 30 MB)
# The folder layout inside is the same as the repo, because the code finds the face models and the classifier by relative path.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"; repo="$(cd "$here/.." && pwd)"
out="${1:-$HOME/Desktop/cashcan_pi_bundle.tar.gz}"
stage="$(mktemp -d)/cashcan_pi_bundle"
mkdir -p "$stage/pi_client" "$stage/face_api/models" "$stage/ml/models"

# 1. the bin program
cp -R "$here/cashcan_pi" "$here/requirements.txt" "$here/README.md" "$stage/pi_client/"
# 2. the face code the bin imports for on-device identity (detection, embedding, matching, sessions) and the two face models (16 MB)
mkdir -p "$stage/face_api/app" && cp "$repo"/face_api/app/*.py "$stage/face_api/app/"
cp "$repo/face_api/models/det_500m.onnx" "$repo/face_api/models/w600k_mbf.onnx" "$stage/face_api/models/"
# 3. the object classifier (FP32 for teaching, INT8 for speed) and its class names
cp "$repo/ml/models/classes.json" "$repo/ml/models/mobilenetv2_cashcan.onnx" "$repo/ml/models/mobilenetv2_cashcan_int8.onnx" "$stage/ml/models/"
find "$stage" -name "__pycache__" -type d -prune -exec rm -rf {} +

cat > "$stage/RUN_ON_PI.md" <<'DOC'
# Put CashCan on the Raspberry Pi (or Radxa) and run it

1. Copy this archive to the board and unpack it:
       scp cashcan_pi_bundle.tar.gz pi@<board-ip>:~ && ssh pi@<board-ip>
       tar xzf cashcan_pi_bundle.tar.gz && cd cashcan_pi_bundle
2. Python packages (64-bit Linux, Python 3.9+):
       python3 -m venv .venv && source .venv/bin/activate
       pip install -r pi_client/requirements.txt
   (If pip cannot find OpenCV or onnxruntime for your board, try: sudo apt install python3-opencv  and  pip install onnxruntime)
3. Run (camera is usually /dev/video0; the key is only needed for the fast on-device mode and for saving records):
       cd pi_client
       python -m cashcan_pi --camera /dev/video0 --classify --local-identity --server https://www.cashcan.biz/face-api --bin-key YOUR_KEY
   Add --show only on a board with a screen. Lids and LEDs: see pi_client/README.md (--lids lids.json, --led-pins).
4. To keep what you taught the bin on your Mac, copy ~/.cashcan/taught.npz (and ~/.cashcan/taught_photos/) to ~/.cashcan/ on the board.
DOC
tar czf "$out" -C "$(dirname "$stage")" cashcan_pi_bundle
echo "wrote $out ($(du -h "$out" | cut -f1))"; tar tzf "$out" | sed 's#^cashcan_pi_bundle/##' | grep -v '/$' | head -60
