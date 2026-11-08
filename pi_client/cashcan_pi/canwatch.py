"""Watch the camera; when it sees a can, open the lid. No can, the lid stays shut.

    sudo python3 -m cashcan_pi.canwatch --camera 0 --chip 0 --channel 0

It looks at every frame with the bin's classifier. The lid opens once the camera has seen a can on a few looks in a row (so one odd frame does nothing),
stays open while the can is still there, and closes `--hold` seconds after the can is gone. Add --dry-run to print servo pulses instead of moving
anything, and --show to see what the camera sees. This is the simple version; the full bin (python -m cashcan_pi --classify --servos ...) also
identifies the person and sorts into three lids. Not yet tried on real hardware.
"""
from __future__ import annotations

import argparse
import sys
import time


class CanWatcher:
    """Pure logic, no camera or servo of its own: feed it the classifier's probabilities, it moves the lid."""

    def __init__(self, lid, bin_name: str = "cans", threshold: float = 0.6, confirm: int = 3, hold: float = 3.0):
        self.lid, self.bin, self.threshold, self.confirm, self.hold = lid, bin_name, threshold, confirm, hold
        self.streak, self.last_seen, self.is_open = 0, -1e9, False

    def update(self, probs: dict, now: float) -> bool:
        """Returns True while the lid is open."""
        if probs.get(self.bin, 0.0) >= self.threshold:
            self.streak += 1
            self.last_seen = now
        else:
            self.streak = 0
        if not self.is_open and self.streak >= self.confirm:
            self.lid.set_open(self.bin, True)
            self.is_open = True
        elif self.is_open and now - self.last_seen >= self.hold:
            self.lid.set_open(self.bin, False)
            self.is_open = False
        return self.is_open


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m cashcan_pi.canwatch", description=__doc__.split("\n\n")[0])
    ap.add_argument("--camera", default="0", help="camera index, device path or video file")
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--model", help="ONNX classifier (default ml/models/mobilenetv2_cashcan_int8.onnx)")
    ap.add_argument("--threshold", type=float, default=0.6, help="how sure the camera must be that it is a can")
    ap.add_argument("--confirm", type=int, default=3, help="looks in a row that must say 'can' before the lid opens")
    ap.add_argument("--hold", type=float, default=3.0, help="seconds the lid stays open after the can is gone")
    ap.add_argument("--fps", type=float, default=5.0, help="how many looks per second")
    ap.add_argument("--chip", type=int, default=0)
    ap.add_argument("--channel", type=int, default=0)
    ap.add_argument("--open-angle", type=float, default=90)
    ap.add_argument("--closed-angle", type=float, default=0)
    ap.add_argument("--dry-run", action="store_true", help="print servo pulses instead of moving the servo")
    ap.add_argument("--show", action="store_true", help="preview window (q to quit)")
    a = ap.parse_args(argv)

    import cv2

    from .classifier import OnnxClassifier
    from .servo import PwmError, make_lid

    lid = make_lid(f"cans={a.chip}:{a.channel}", a.open_angle, a.closed_angle, dry_run=a.dry_run)
    watcher = CanWatcher(lid, "cans", a.threshold, a.confirm, a.hold)
    clf = OnnxClassifier(a.model)
    src = a.camera
    cam = cv2.VideoCapture(int(src) if src.isdigit() else src)
    if src.isdigit():
        cam.set(cv2.CAP_PROP_FRAME_WIDTH, a.width)
        cam.set(cv2.CAP_PROP_FRAME_HEIGHT, a.height)
    if not cam.isOpened():
        print(f"canwatch: cannot open camera {src}", file=sys.stderr)
        return 1
    print("canwatch: watching for cans (Ctrl-C to stop)", file=sys.stderr)
    was_open, period = False, 1.0 / max(a.fps, 0.1)
    try:
        while True:
            t0 = time.monotonic()
            ok, frame = cam.read()
            if not ok:
                print("canwatch: camera stopped giving frames", file=sys.stderr)
                return 1
            probs = clf.probs(frame)
            try:
                now_open = watcher.update(probs, time.monotonic())
            except PwmError as e:
                print(f"canwatch: {e}", file=sys.stderr)
                return 1
            if now_open != was_open:
                print("canwatch: can seen, lid OPEN" if now_open else "canwatch: can gone, lid closed", file=sys.stderr, flush=True)
                was_open = now_open
            if a.show:
                cv2.putText(frame, f"can {probs.get('cans', 0):.2f}  lid {'OPEN' if now_open else 'shut'}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9,
                            (0, 200, 0) if now_open else (0, 0, 255), 2)
                cv2.imshow("canwatch", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
            time.sleep(max(0.0, period - (time.monotonic() - t0)))
    except KeyboardInterrupt:
        pass
    finally:
        cam.release()
        lid.set_open("cans", False)       # leave the lid shut
    return 0


if __name__ == "__main__":
    sys.exit(main())
