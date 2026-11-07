"""Try the face recognition on your own laptop (macOS or Linux): save your face, then test it.

  python -m tools.face_demo enroll   --name junaid                 # webcam, 5 frames
  python -m tools.face_demo enroll   --name junaid --images ~/me/*.jpg
  python -m tools.face_demo identify --image photo1.jpg group.png  # who is in these pictures?
  python -m tools.face_demo identify --webcam                      # live; press q to quit
  python -m tools.face_demo evaluate --name junaid --mine ~/test/me --others ~/test/others
  python -m tools.face_demo list | delete --name junaid

Faces are stored as 512-number templates (no photos) in a local SQLite file (--db, default
cashcan_faces.db), the same file the API and enrollment web page use. Matching uses the same
threshold and ambiguity rule as the bin. Add --no-window on a machine without a display.
"""
from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from app import config
from app.face_engine import FaceEngine, FaceResult, QualityError, check_quality, decode_image, pick_face
from app.matching import match
from app.store import FaceStore

PLACEHOLDER_WALLET = "DEMO-NO-WALLET"  # the API requires a wallet; the demo has none
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


@dataclass
class FaceReport:
    box: tuple[int, int, int, int]
    usable: bool
    message: str = ""            # why a face was skipped (quality gate)
    matched: bool = False
    name: str | None = None
    score: float = 0.0
    reason: str = ""             # below_threshold | ambiguous | no_enrolled_users | ok
    ranking: list[tuple[str, float]] = field(default_factory=list)  # best score per enrolled person

    @property
    def label(self) -> str:
        if not self.usable:
            return f"skipped: {self.message}"
        return f"{self.name} {self.score:.2f}" if self.matched else f"unknown ({self.reason}, best {self.score:.2f})"


def ranking(emb: np.ndarray, owners: list[str], gallery: np.ndarray) -> list[tuple[str, float]]:
    best: dict[str, float] = {}
    for o, s in zip(owners, gallery @ emb):
        best[o] = max(best.get(o, -1.0), float(s))
    return sorted(best.items(), key=lambda kv: kv[1], reverse=True)


def report_for(face: FaceResult, owners, gallery, threshold, margin) -> FaceReport:
    try:
        check_quality(face)
    except QualityError as e:
        return FaceReport(face.box, False, str(e))
    r = match(face.embedding, owners, gallery, threshold=threshold, margin=margin)
    return FaceReport(face.box, True, "", r.matched, r.user_id, r.score, r.reason,
                      ranking(face.embedding, owners, gallery)[:3] if len(owners) else [])


def identify_frame(engine: FaceEngine, store: FaceStore, img: np.ndarray,
                   threshold: float, margin: float) -> list[FaceReport]:
    owners, gallery = store.all_embeddings()
    return [report_for(f, owners, gallery, threshold, margin) for f in engine.analyse(img)]


def annotate(img: np.ndarray, reports: list[FaceReport]) -> np.ndarray:
    import cv2

    out = img.copy()
    for r in reports:
        x1, y1, x2, y2 = r.box
        colour = (0, 180, 0) if r.matched else (0, 140, 255) if r.usable else (128, 128, 128)
        cv2.rectangle(out, (x1, y1), (x2, y2), colour, 2)
        short = r.label if not r.usable else (f"{r.name} {r.score:.2f}" if r.matched else f"unknown {r.score:.2f}")
        cv2.putText(out, short if r.usable else "skipped", (x1, max(y1 - 8, 14)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, colour, 2)
    return out


def list_images(paths: list[str]) -> list[Path]:
    found: list[Path] = []
    for p in map(Path, paths):
        found += sorted(f for f in p.rglob("*") if f.suffix.lower() in IMAGE_EXT) if p.is_dir() else [p]
    return found


def largest_usable(engine: FaceEngine, img: np.ndarray) -> FaceResult:
    face = pick_face(engine.analyse(img))  # raises QualityError("No face found...")
    check_quality(face)
    return face


# ---------------------------------------------------------------- commands
def cmd_enroll(a, engine, store) -> int:
    name = a.name
    if store.user_exists(name):
        print(f"'{name}' is already saved. Run `delete --name {name}` first to re-enroll.", file=sys.stderr)
        return 1
    embs: list[np.ndarray] = []
    if a.images:
        for p in list_images(a.images):
            try:
                embs.append(largest_usable(engine, decode_image(p.read_bytes())).embedding)
            except QualityError as e:
                print(f"  skip {p.name}: {e}")
    else:
        embs = capture_from_camera(a, engine)
    if len(embs) < config.MIN_ENROLL_FRAMES:
        print(f"Only {len(embs)} usable frame(s); need {config.MIN_ENROLL_FRAMES}. Nothing saved.", file=sys.stderr)
        return 1
    store.add_user(name, PLACEHOLDER_WALLET, embs[: config.MAX_ENROLL_FRAMES])
    print(f"Saved '{name}' with {min(len(embs), config.MAX_ENROLL_FRAMES)} face templates -> {a.db}")
    return 0


PROMPTS = ["Look straight at the camera", "Turn slightly left", "Turn slightly right",
           "Lift your chin a little", "Look straight again", "Tilt your head slightly", "Smile", "Neutral face"]


def open_camera(src: str):
    import cv2

    cam = cv2.VideoCapture(int(src) if src.isdigit() else src)
    if not cam.isOpened():
        raise SystemExit(f"Cannot open camera '{src}'. On macOS allow camera access for your terminal "
                         "(System Settings > Privacy & Security > Camera); try --camera 1 if 0 is your phone.")
    return cam


def show(window: str, frame, no_window: bool) -> bool:
    """Returns True if the user pressed q."""
    if no_window:
        return False
    import cv2

    try:
        cv2.imshow(window, frame)
    except cv2.error:
        raise SystemExit("No GUI available in this OpenCV build. Install the windowed build: "
                         "pip uninstall -y opencv-python-headless && pip install opencv-python  (or use --no-window)")
    return (cv2.waitKey(1) & 0xFF) == ord("q")


def capture_from_camera(a, engine) -> list[np.ndarray]:
    import cv2

    cam, got, last = open_camera(a.camera), [], 0.0
    print(f"Capturing {a.count} frames. Follow the on-screen prompts. Press q to stop.")
    deadline = time.time() + 60
    while len(got) < a.count and time.time() < deadline:
        ok, frame = cam.read()
        if not ok:
            break
        msg = PROMPTS[len(got) % len(PROMPTS)]
        try:
            face = largest_usable(engine, frame)
            if time.time() - last >= a.interval:
                got.append(face.embedding)
                last = time.time()
        except QualityError as e:
            msg = str(e)
        view = frame.copy()
        cv2.putText(view, f"{len(got)}/{a.count}  {msg}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 200, 0), 2)
        if show("enroll (q = stop)", view, a.no_window):
            break
    cam.release()
    if not a.no_window:
        cv2.destroyAllWindows()
    return got


def cmd_identify(a, engine, store) -> int:
    import cv2

    if store.all_embeddings()[0] == []:
        print("Nobody is enrolled yet. Run `enroll` first.", file=sys.stderr)
        return 1
    if a.webcam:
        return live(a, engine, store)
    out_dir = Path(a.annotate) if a.annotate else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
    for p in list_images(a.image or []):
        try:
            img = decode_image(p.read_bytes())
        except QualityError as e:
            print(f"{p.name}: {e}")
            continue
        reports = identify_frame(engine, store, img, a.threshold, a.margin)
        print(f"{p.name}: {len(reports)} face(s)" + ("" if reports else "  (no face found)"))
        for i, r in enumerate(reports, 1):
            tops = "  top: " + ", ".join(f"{n} {s:.2f}" for n, s in r.ranking) if r.usable else ""
            print(f"  face {i}: {r.label}{tops}")
        if out_dir:
            cv2.imwrite(str(out_dir / f"{p.stem}_result.png"), annotate(img, reports))
    if out_dir:
        print(f"Annotated copies saved in {out_dir}/")
    return 0


def live(a, engine, store) -> int:
    cam, n, reports, t0 = open_camera(a.camera), 0, [], time.time()
    last_print = ""
    print("Live identify. Press q in the window to quit." if not a.no_window else "Live identify (Ctrl+C to stop).")
    try:
        while True:
            ok, frame = cam.read()
            if not ok:
                if a.camera.isdigit():
                    break
                cam.set(1, 0)  # loop a video file
                continue
            n += 1
            if n % a.every == 0:
                reports = identify_frame(engine, store, frame, a.threshold, a.margin)
                line = " | ".join(r.label for r in reports) or "no face"
                if a.no_window and line != last_print:
                    print(line, flush=True)
                last_print = line
            if show("identify (q = quit)", annotate(frame, reports), a.no_window):
                break
            if a.max_seconds and time.time() - t0 > a.max_seconds:
                break
    except KeyboardInterrupt:
        pass
    finally:
        cam.release()
    return 0


def cmd_evaluate(a, engine, store) -> int:
    """Your photos should match you; other people's photos should not."""
    if not store.user_exists(a.name):
        print(f"'{a.name}' is not enrolled.", file=sys.stderr)
        return 1
    owners, gallery = store.all_embeddings()
    rows: list[tuple[str, str, str]] = []  # (kind, file, outcome)
    scores: dict[str, list[float]] = {"mine": [], "others": []}
    unusable = {"mine": 0, "others": 0}
    for kind, paths in (("mine", a.mine), ("others", a.others)):
        for p in list_images(paths or []):
            try:
                face = largest_usable(engine, decode_image(p.read_bytes()))
            except QualityError as e:
                unusable[kind] += 1
                rows.append((kind, p.name, f"unusable: {e}"))
                continue
            r = match(face.embedding, owners, gallery, threshold=a.threshold, margin=a.margin)
            mine_score = dict(ranking(face.embedding, owners, gallery)).get(a.name, 0.0)
            scores[kind].append(mine_score)
            if r.matched:
                outcome = f"matched {r.user_id} ({r.score:.2f})"
            else:
                outcome = f"not recognised ({r.reason}, your score {mine_score:.2f})"
            rows.append((kind, p.name, outcome))
    mine_ok = sum(1 for k, _, o in rows if k == "mine" and o.startswith(f"matched {a.name} "))
    mine_n = len(scores["mine"])
    oth_hit = sum(1 for k, _, o in rows if k == "others" and o.startswith(f"matched {a.name} "))
    oth_wrong = sum(1 for k, _, o in rows if k == "others" and o.startswith("matched ") and not o.startswith(f"matched {a.name} "))
    oth_n = len(scores["others"])
    print(f"\nthreshold {a.threshold}, margin {a.margin}\n")
    for kind, fname, outcome in rows:
        good = (kind == "mine" and outcome.startswith(f"matched {a.name} ")) or \
               (kind == "others" and not outcome.startswith("matched") and not outcome.startswith("unusable")) or outcome.startswith("unusable")
        print(f"  [{'ok ' if good else 'ERR'}] {kind:6} {fname}: {outcome}")
    print()
    if mine_n:
        s = scores["mine"]
        print(f"Your photos:   {mine_ok}/{mine_n} recognised as {a.name}   (your score: min {min(s):.2f}, mean {np.mean(s):.2f})")
    if oth_n:
        s = scores["others"]
        print(f"Other people:  {oth_hit}/{oth_n} wrongly accepted as {a.name}   (your score on them: max {max(s):.2f})")
        if oth_wrong:
            print(f"               {oth_wrong} matched a different enrolled person")
    if unusable["mine"] or unusable["others"]:
        print(f"Unusable photos (no face / too small / blurry): mine {unusable['mine']}, others {unusable['others']}")
    if mine_n and oth_n:
        lo, hi = min(scores["mine"]), max(scores["others"])
        if lo > hi:
            print(f"\nClean gap between you ({lo:.2f}) and others ({hi:.2f}): any threshold in between works; "
                  f"{(lo + hi) / 2:.2f} is the middle. Current {a.threshold}.")
        else:
            print(f"\nScores overlap (your lowest {lo:.2f} vs others' highest {hi:.2f}): no threshold separates these photos perfectly.")
    print("\nSmall tests prove little: a handful of photos cannot show a rate below roughly 3/N.")
    return 0 if (mine_ok == mine_n and oth_hit + oth_wrong == 0) else 2


def cmd_list(a, engine, store) -> int:
    owners, _ = store.all_embeddings()
    if not owners:
        print("(nobody enrolled)")
    for o in sorted(set(owners)):
        print(f"{o}: {owners.count(o)} templates")
    return 0


def cmd_delete(a, engine, store) -> int:
    if store.delete_user(a.name):
        print(f"Deleted '{a.name}' and all their face templates.")
        return 0
    print(f"'{a.name}' not found.", file=sys.stderr)
    return 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=config.DB_PATH)
    ap.add_argument("--threshold", type=float, default=config.MATCH_THRESHOLD)
    ap.add_argument("--margin", type=float, default=config.AMBIGUITY_MARGIN)
    sub = ap.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("enroll"); e.add_argument("--name", required=True)
    e.add_argument("--images", nargs="+"); e.add_argument("--count", type=int, default=5)
    e.add_argument("--camera", default="0"); e.add_argument("--interval", type=float, default=1.0)
    e.add_argument("--no-window", action="store_true"); e.set_defaults(fn=cmd_enroll)

    i = sub.add_parser("identify"); i.add_argument("--image", nargs="+"); i.add_argument("--webcam", action="store_true")
    i.add_argument("--camera", default="0"); i.add_argument("--every", type=int, default=2)
    i.add_argument("--annotate", metavar="DIR"); i.add_argument("--no-window", action="store_true")
    i.add_argument("--max-seconds", type=float, default=0); i.set_defaults(fn=cmd_identify)

    v = sub.add_parser("evaluate"); v.add_argument("--name", required=True)
    v.add_argument("--mine", nargs="+"); v.add_argument("--others", nargs="+"); v.set_defaults(fn=cmd_evaluate)

    sub.add_parser("list").set_defaults(fn=cmd_list)
    d = sub.add_parser("delete"); d.add_argument("--name", required=True); d.set_defaults(fn=cmd_delete)

    a = ap.parse_args(argv)
    from app.face_engine import InsightFaceEngine

    engine = None if a.cmd in ("list", "delete") else InsightFaceEngine()
    return a.fn(a, engine, FaceStore(a.db))


if __name__ == "__main__":
    sys.exit(main())
