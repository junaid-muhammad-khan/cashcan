"""Tune the face-match threshold on real faces.

  python -m tools.tune capture --person alice --tag enroll --count 5
  python -m tools.tune capture --person alice --tag dim    --count 10
  python -m tools.tune capture --person alice --tag glasses --count 10
  (repeat for each teammate, ideally 3+ people)
  python -m tools.tune report

Only embeddings are saved (tuning_data/<person>/<tag>.npy), never photos.
Tag "enroll" = the gallery (like a real enrollment). Every other tag = probes.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

from app import config
from app.face_engine import QualityError, check_quality, pick_face
from app.tuning import Probe, recommend, score_stats, sweep

DATA = Path("tuning_data")
SAFE_FLOOR = 0.35  # never suggest below this, however clean a small dataset looks


def save(person: str, tag: str, embs: list[np.ndarray]) -> Path:
    path = DATA / person / f"{tag}.npy"
    path.parent.mkdir(parents=True, exist_ok=True)
    old = np.load(path) if path.exists() else np.zeros((0, 512), np.float32)
    np.save(path, np.concatenate([old, np.stack(embs)]).astype(np.float32))
    return path


def cmd_capture(a) -> int:
    import cv2
    from app.face_engine import InsightFaceEngine

    engine = InsightFaceEngine()
    cam = cv2.VideoCapture(a.camera)
    if not cam.isOpened():
        print(f"Cannot open camera {a.camera}", file=sys.stderr)
        return 1
    got: list[np.ndarray] = []
    last = 0.0
    print(f"Capturing {a.count} frames for {a.person} [{a.tag}]. Vary your pose slightly. Press q to stop.")
    while len(got) < a.count:
        ok, frame = cam.read()
        if not ok:
            break
        msg, colour = "no face", (0, 0, 255)
        try:
            face = pick_face(engine.analyse(frame))
            check_quality(face)
            msg, colour = "ok", (0, 200, 0)
            if time.time() - last >= a.interval:
                got.append(face.embedding)
                last = time.time()
        except QualityError as e:
            msg = str(e)
        if not a.no_window:
            cv2.putText(frame, f"{a.person}/{a.tag} {len(got)}/{a.count}: {msg}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, colour, 2)
            cv2.imshow("tune", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    cam.release()
    if not a.no_window:
        cv2.destroyAllWindows()
    if not got:
        print("Nothing captured.", file=sys.stderr)
        return 1
    print(f"Saved {len(got)} embeddings -> {save(a.person, a.tag, got)}")
    return 0


def cmd_ingest(a) -> int:
    """Same as capture but from a folder of images (useful without a webcam)."""
    from app.face_engine import InsightFaceEngine, decode_image

    engine, got = InsightFaceEngine(), []
    for img in sorted(Path(a.dir).iterdir()):
        try:
            face = pick_face(engine.analyse(decode_image(img.read_bytes())))
            check_quality(face)
            got.append(face.embedding)
        except QualityError as e:
            print(f"skip {img.name}: {e}")
    if not got:
        print("Nothing usable.", file=sys.stderr)
        return 1
    print(f"Saved {len(got)} embeddings -> {save(a.person, a.tag, got)}")
    return 0


def load():
    enroll, probes = {}, []
    for pdir in sorted(p for p in DATA.glob("*") if p.is_dir()):
        for f in sorted(pdir.glob("*.npy")):
            embs = np.load(f)
            if f.stem == "enroll":
                enroll[pdir.name] = embs
            else:
                probes += [Probe(pdir.name, f.stem, e) for e in embs]
    return enroll, probes


def cmd_report(a) -> int:
    enroll, probes = load()
    if len(enroll) < 2 or not probes:
        print("Need an 'enroll' set for at least 2 people plus probe sets (other tags). "
              "See the usage at the top of tools/tune.py.", file=sys.stderr)
        return 1
    gen, imp, per_tag = score_stats(enroll, probes)
    print(f"{len(enroll)} people, {len(probes)} probes, {len(gen)} genuine / {len(imp)} impostor comparisons\n")
    print(f"genuine  scores: min {gen.min():.2f}  p5 {np.percentile(gen, 5):.2f}  mean {gen.mean():.2f}")
    print(f"impostor scores: max {imp.max():.2f}  p95 {np.percentile(imp, 95):.2f}  mean {imp.mean():.2f}")
    print("\ngenuine by condition (min / mean):")
    for tag, v in sorted(per_tag.items()):
        print(f"  {tag:<12} {min(v):.2f} / {np.mean(v):.2f}  (n={len(v)})")
    rows = sweep(enroll, probes, np.arange(0.20, 0.75, 0.05), config.AMBIGUITY_MARGIN)
    print(f"\n{'thresh':>6} {'FRR':>7} {'wrong':>7} {'FAR':>7}   (margin {config.AMBIGUITY_MARGIN})")
    for r in rows:
        far = "n/a" if r.far is None else f"{r.far:.1%}"
        mark = "  <- current" if abs(r.threshold - config.MATCH_THRESHOLD) < 1e-6 else ""
        print(f"{r.threshold:>6.2f} {r.frr:>7.1%} {r.wrong_user:>7.1%} {far:>7}{mark}")
    rec = recommend(rows)
    print()
    if gen.min() > imp.max():
        mid = max(round(float((gen.min() + imp.max()) / 2), 2), SAFE_FLOOR)
        print(f"Scores are fully separable (gap {imp.max():.2f} - {gen.min():.2f}). "
              f"Suggested MATCH_THRESHOLD: {mid} (middle of the gap, floor {SAFE_FLOOR}).")
    elif rec:
        t = max(rec.threshold, SAFE_FLOOR)
        print(f"Scores overlap. Suggested MATCH_THRESHOLD: {t} (lowest with FAR <= 1%, FRR {rec.frr:.1%}).")
    else:
        print("No tested threshold reached FAR <= 1%. Collect more data, or the model is not good enough here.")
    print(f"Caveat: with {len(probes)} probes, a measured 0% FAR only shows FAR is below roughly "
          f"{3 / len(probes):.0%} (rule of three). Say this honestly when presenting.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in (("capture", cmd_capture), ("ingest", cmd_ingest)):
        p = sub.add_parser(name)
        p.add_argument("--person", required=True)
        p.add_argument("--tag", default="enroll")
        if name == "capture":
            p.add_argument("--count", type=int, default=10)
            p.add_argument("--camera", type=int, default=0)
            p.add_argument("--interval", type=float, default=0.5, help="seconds between saved frames")
            p.add_argument("--no-window", action="store_true")
        else:
            p.add_argument("--dir", required=True)
        p.set_defaults(fn=fn)
    sub.add_parser("report").set_defaults(fn=cmd_report)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
