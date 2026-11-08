"""Measure how often each registered person is recognised from their Databricks templates, over many real camera frames.

  export DATABRICKS_HOST=... DATABRICKS_TOKEN=... DATABRICKS_WAREHOUSE_ID=...
  python -m tools.probe_people capture --person junaid --frames 100          # person sits at the camera, ~1-2 minutes
  python -m tools.probe_people capture --person person-1 --frames 100        # then each friend, on the same camera
  python -m tools.probe_people report --out PROBE_REPORT.md

Each frame goes through the same steps as the bin: detect -> lenient identification gates -> match() against the templates pulled
from Databricks (threshold and ambiguity margin from config). Per frame it records one outcome:
  correct      the right person was returned
  wrong_name   somebody else was returned (the dangerous one: money would go to the wrong wallet)
  unknown      nobody cleared the threshold / ambiguity rule
  skipped      the frame failed the quality gates (too small, blurry, no face): at the bin the person would just retry
Only outcomes and scores are saved (probe_runs/<person>.json), never photos or embeddings.
The prompts rotate through distance, head angle and light so the 100 frames are not 100 copies of one pose.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

from app import config
from app.matching import match

RUNS = Path("probe_runs")
PROMPTS = ["Sit normally, look at the camera.", "Move a little closer.", "Lean back (arm's length).",
           "Turn your head slightly left.", "Turn your head slightly right.", "Look slightly down, then up.",
           "Make the light worse (dim a lamp or sit by a window).", "Smile / change expression."]


def score_frame(emb: np.ndarray, owners: list[str], gallery: np.ndarray, expected: str,
                threshold: float | None = None, margin: float | None = None) -> dict:
    """Outcome of one usable frame: {outcome, right (best score of the expected person), wrong (best score of anybody else)}."""
    own = [i for i, o in enumerate(owners) if o == expected]
    oth = [i for i, o in enumerate(owners) if o != expected]
    right = float((gallery[own] @ emb).max()) if own else 0.0
    wrong = float((gallery[oth] @ emb).max()) if oth else 0.0
    res = match(emb, owners, gallery, **({"threshold": threshold} if threshold is not None else {}),
                **({"margin": margin} if margin is not None else {}))
    outcome = "unknown" if not res.matched else ("correct" if res.user_id == expected else "wrong_name")
    return {"outcome": outcome, "right": round(right, 4), "wrong": round(wrong, 4)}


def summarise(rows: list[dict]) -> dict:
    n = len(rows)
    used = [r for r in rows if r["outcome"] != "skipped"]
    count = lambda k: sum(1 for r in rows if r["outcome"] == k)
    rights = [r["right"] for r in used]
    return {"frames": n, "correct": count("correct"), "wrong_name": count("wrong_name"), "unknown": count("unknown"),
            "skipped": count("skipped"),
            "right_min": min(rights, default=0.0), "right_median": float(np.median(rights)) if rights else 0.0,
            "wrong_max": max((r["wrong"] for r in used), default=0.0)}


def render(runs: dict[str, list[dict]], threshold: float, margin: float) -> str:
    pc = lambda a, b: f"{100 * a / b:.0f}%" if b else "n/a"
    lines = [f"# Registered people: recognition over real camera frames\n",
             f"Threshold {threshold:.0%}, ambiguity margin {margin:.0%}. Templates pulled from Databricks. One camera, one session per person; "
             "who was at the camera is as reported by the tester.\n",
             "| Person | Frames | Recognised (all frames) | Recognised (frames that passed the gates) | Wrong name | Unknown | Skipped by gates | Right-person score min / median | Highest wrong-person score |",
             "|---|---|---|---|---|---|---|---|---|"]
    tot = {"frames": 0, "correct": 0, "wrong_name": 0, "unknown": 0, "skipped": 0}
    for person, rows in sorted(runs.items()):
        s = summarise(rows)
        used = s["frames"] - s["skipped"]
        lines.append(f"| {person} | {s['frames']} | {s['correct']} ({pc(s['correct'], s['frames'])}) | {s['correct']}/{used} ({pc(s['correct'], used)}) | "
                     f"{s['wrong_name']} | {s['unknown']} | {s['skipped']} | {s['right_min']:.0%} / {s['right_median']:.0%} | {s['wrong_max']:.0%} |")
        for k in tot:
            tot[k] += s[k]
    used = tot["frames"] - tot["skipped"]
    lines.append(f"| **All** | {tot['frames']} | {tot['correct']} ({pc(tot['correct'], tot['frames'])}) | {tot['correct']}/{used} ({pc(tot['correct'], used)}) | "
                 f"{tot['wrong_name']} | {tot['unknown']} | {tot['skipped']} | | |")
    lines.append("\nWrong name means the frame was matched to a different registered person. Unknown means no one cleared the threshold: at the bin the person retries.")
    return "\n".join(lines) + "\n"


def cmd_capture(a) -> int:
    from app.databricks_store import DatabricksFaces
    from app.lean_engine import LeanEngine
    from app.face_engine import QualityError, check_quality
    from tools.face_demo import grab, largest_usable, open_camera

    owners, gallery, _ = DatabricksFaces().pull_all()
    if a.person not in set(owners):
        print(f"'{a.person}' is not in Databricks. People there: {sorted(set(owners))}", file=sys.stderr)
        return 1
    engine, cam, rows = LeanEngine(), open_camera(a.camera), []
    print(f"Capturing {a.frames} frames of {a.person}. Follow the prompts; Ctrl+C stops early and keeps what was captured.")
    try:
        t0, shown = time.time(), -1
        while len(rows) < a.frames:
            if len(rows) % a.per_prompt == 0 and len(rows) != shown:
                shown = len(rows)
                print(f"[{len(rows)}/{a.frames}] {PROMPTS[(len(rows) // a.per_prompt) % len(PROMPTS)]}")
            frame = grab(cam, a.camera.isdigit(), timeout=3.0)
            if frame is None:
                print("Camera gave no frame.", file=sys.stderr)
                break
            if time.time() - t0 < 1.0:  # auto-exposure warm-up
                continue
            try:
                face = largest_usable(engine, frame, identification=True)
                rows.append(score_frame(face.embedding, owners, gallery, a.person))
            except QualityError:
                rows.append({"outcome": "skipped", "right": 0.0, "wrong": 0.0})
            time.sleep(a.gap)
    except KeyboardInterrupt:
        pass
    finally:
        cam.release()
    RUNS.mkdir(exist_ok=True)
    (RUNS / f"{a.person}.json").write_text(json.dumps(rows))
    s = summarise(rows)
    print(f"{a.person}: {s['correct']}/{s['frames']} recognised, {s['wrong_name']} wrong name, {s['unknown']} unknown, {s['skipped']} skipped by gates.")
    return 0


def cmd_report(a) -> int:
    runs = {p.stem: json.loads(p.read_text()) for p in sorted(RUNS.glob("*.json"))}
    if not runs:
        print("No runs yet. Run `capture` for each person first.", file=sys.stderr)
        return 1
    text = render(runs, config.MATCH_THRESHOLD, config.AMBIGUITY_MARGIN)
    print(text)
    if a.out:
        Path(a.out).write_text(text)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("capture")
    c.add_argument("--person", required=True)
    c.add_argument("--frames", type=int, default=100)
    c.add_argument("--camera", default="0")
    c.add_argument("--gap", type=float, default=0.4, help="seconds between frames")
    c.add_argument("--per-prompt", type=int, default=13, help="frames per pose prompt")
    r = sub.add_parser("report"); r.add_argument("--out")
    a = ap.parse_args(argv)
    return cmd_capture(a) if a.cmd == "capture" else cmd_report(a)


if __name__ == "__main__":
    sys.exit(main())
