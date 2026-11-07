"""Run the bin identity loop:  python -m cashcan_pi --server http://192.168.1.20:8000

Events are printed to stdout as JSON lines (session_started, session_ended, denied, error), so the
payout / classifier process can read them. Human-readable status goes to stderr.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import cv2

from .api import FaceApi
from .detector import make_detector
from .indicator import ConsoleIndicator, GpioIndicator
from .loop import BinLoop


def open_camera(src: str, width: int, height: int):
    cam = cv2.VideoCapture(int(src) if src.isdigit() else src)  # index, device path or video file
    if src.isdigit():
        cam.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cam.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    return cam


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--server", default=os.environ.get("CASHCAN_SERVER", "http://localhost:8000"))
    ap.add_argument("--camera", default=os.environ.get("CASHCAN_CAMERA", "0"),
                    help="camera index, device path, or a video file for testing (loops)")
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--send-interval", type=float, default=0.7)
    ap.add_argument("--recheck-interval", type=float, default=5.0)
    ap.add_argument("--led-pins", metavar="GREEN,RED,AMBER", help="BCM pins; needs gpiozero (on the Pi)")
    a = ap.parse_args(argv)

    ind = ConsoleIndicator()
    if a.led_pins:
        g, r, y = (int(p) for p in a.led_pins.split(","))
        ind = GpioIndicator(g, r, y)
    emit = lambda e: print(json.dumps(e), flush=True)
    loop = BinLoop(FaceApi(a.server), make_detector(warn=lambda m: print(m, file=sys.stderr)), ind, emit,
                   send_interval=a.send_interval, recheck_interval=a.recheck_interval)

    is_file = not a.camera.isdigit() and os.path.isfile(a.camera)
    cam, fails = open_camera(a.camera, a.width, a.height), 0
    print(f"cashcan_pi: camera={a.camera} server={a.server}", file=sys.stderr)
    try:
        while True:
            ok, frame = cam.read()
            if not ok:
                if is_file:
                    cam.set(cv2.CAP_PROP_POS_FRAMES, 0)  # loop the test video
                    continue
                fails += 1
                ind.set("error", "camera not readable")
                time.sleep(0.5)
                if fails >= 20:  # camera unplugged / hung: reopen
                    cam.release()
                    cam, fails = open_camera(a.camera, a.width, a.height), 0
                continue
            fails = 0
            loop.step(frame, time.monotonic())
            time.sleep(0.05)
    except KeyboardInterrupt:
        return 0
    finally:
        cam.release()


if __name__ == "__main__":
    sys.exit(main())
