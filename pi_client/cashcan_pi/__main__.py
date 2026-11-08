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
    ap.add_argument("--no-face-precheck", action="store_true", help="send every frame to the server instead of only when the local Haar check sees a face")
    ap.add_argument("--led-pins", metavar="GREEN,RED,AMBER", help="BCM pins; needs gpiozero (on the Pi)")
    ap.add_argument("--liveness", action="store_true", help="with --local-identity: after a face is recognised, also ask for a head turn (off by default: the bin verifies on the face match alone)")
    ap.add_argument("--no-liveness", action="store_true", help=argparse.SUPPRESS)  # old spelling: now the default
    ap.add_argument("--local-identity", action="store_true", help="identify people on this device (fast, works offline) using a gallery downloaded from the server with --bin-key")
    g = ap.add_argument_group("object classifier + lids (turns the identity loop into the full bin controller)")
    g.add_argument("--classify", action="store_true", help="also classify the item on the same camera and open the right lid")
    g.add_argument("--model", help="ONNX classifier (default ml/models/mobilenetv2_cashcan.onnx)")
    g.add_argument("--bin-key", default=os.environ.get("CASHCAN_BIN_KEY"), help="this bin's key (X-Bin-Key) for POST /interactions")
    g.add_argument("--item-roi", default="0.15,0.40,0.85,1.0", help="x1,y1,x2,y2 as fractions of the frame: where items are held or dropped")
    g.add_argument("--min-confidence", type=float, default=0.60, help="below this the item goes to the waste lid and earns nothing")
    g.add_argument("--lid-seconds", type=float, default=6.0)
    g.add_argument("--show", action="store_true", help="open a preview window with the bin's decisions drawn on the camera frame (q to quit)")
    g.add_argument("--save-items", metavar="DIR", help="save a photo of every item the bin classifies, with the decision in the file name (to retrain on this camera)")
    g.add_argument("--lids", metavar="FILE.json", help='{"cans": {"open": "cmd", "close": "cmd"}, ...}; omit to simulate lids on stderr')
    a = ap.parse_args(argv)

    ind = ConsoleIndicator()
    if a.led_pins:
        g, r, y = (int(p) for p in a.led_pins.split(","))
        ind = GpioIndicator(g, r, y)
    emit = lambda e: print(json.dumps(e), flush=True)
    from .detector import AlwaysDetector
    from .threaded import BackgroundIdentity

    api = FaceApi(a.server, bin_key=a.bin_key)
    import threading

    threading.Thread(target=lambda: print("cashcan_pi: server warm" if api.warm() else "cashcan_pi: server did not answer /warm", file=sys.stderr),
                     daemon=True).start()   # wake the face server now so the first match is not the slow one
    detector = AlwaysDetector() if a.no_face_precheck else make_detector(warn=lambda m: print(m, file=sys.stderr))
    loop_api = api
    if a.local_identity:
        from .local import Gallery, LocalApi

        gallery = Gallery(api._http)
        gallery.maybe_refresh(0.0)
        print(f"cashcan_pi: local identity, {len(set(gallery.owners))} people in the gallery", file=sys.stderr)
        loop_api = LocalApi(gallery, require_liveness=bool(a.liveness))
        print("cashcan_pi: head-turn check is " + ("ON" if a.liveness else "OFF: a recognised face is verified from the match alone"), file=sys.stderr)
    loop = BinLoop(loop_api, detector, ind, emit,
                   send_interval=a.send_interval, recheck_interval=a.recheck_interval)
    loop = BackgroundIdentity(loop)   # server calls run on their own thread: the camera and the window never wait on them
    runner, roi = loop, (0.15, 0.40, 0.85, 1.0)
    if a.classify:
        from .classifier import OnnxClassifier
        from .controller import BinController, Outbox
        from .itemgate import ItemGate
        from .lid import CommandLid, LidController, SimulatedLid

        if not a.bin_key:
            print("cashcan_pi: no --bin-key / CASHCAN_BIN_KEY: items will be sorted but the server will refuse the records", file=sys.stderr)
        roi = tuple(float(v) for v in a.item_roi.split(","))
        driver = CommandLid(json.loads(open(a.lids).read())) if a.lids else SimulatedLid()
        runner = BinController(loop, ItemGate(roi=roi), OnnxClassifier(a.model), LidController(driver, a.lid_seconds),
                               Outbox(api, on_event=emit), emit, min_confidence=a.min_confidence, save_dir=a.save_items)

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
            now = time.monotonic()
            runner.step(frame, now)
            if a.show:
                from .preview import draw

                if a.classify:
                    st = runner.status(now)
                else:
                    sess = loop.current_session(now)
                    st = {"user_id": sess.user_id if sess else None, "gate": "-", "collecting_looks": False, "open_lid": None,
                          "last_item": None, "identity": loop.info()}
                try:
                    cv2.imshow("cashcan bin test (q to quit)", draw(frame, st, ind.state, ind.message, roi))
                except cv2.error:
                    print("cashcan_pi: --show needs a GUI build of OpenCV: pip uninstall -y opencv-python-headless && pip install 'opencv-python<5'", file=sys.stderr)
                    return 2
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
            time.sleep(0.02 if a.show else 0.05)
    except KeyboardInterrupt:
        return 0
    finally:
        cam.release()
        loop.stop()


if __name__ == "__main__":
    sys.exit(main())
