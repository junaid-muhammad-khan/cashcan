"""Try the face recognition on your own laptop (macOS or Linux): save your face, then test it.

  python -m tools.face_demo enroll   --name junaid                 # webcam, 5 frames
  python -m tools.face_demo enroll   --name junaid --add --guided  # add webcam frames covering distance and light (raises scores)
  python -m tools.face_demo enroll   --name junaid --images ~/me/*.jpg
  python -m tools.face_demo identify --image photo1.jpg group.png  # who is in these pictures?
  python -m tools.face_demo identify --webcam                      # live; press q to quit
  python -m tools.face_demo identify --webcam --debug              # also show why a frame is skipped, in numbers
  python -m tools.face_demo evaluate --name junaid --mine ~/test/me --others ~/test/others
  python -m tools.face_demo selftest --outsider                     # everyone steps up in turn: PASS or FAIL for each
  python -m tools.face_demo list | delete --name junaid

Faces are stored as 512-number templates (no photos) in a local SQLite file (--db, default
cashcan_faces.db), the same file the API and enrollment web page use. Matching uses the same
threshold and ambiguity rule as the bin. Add --no-window on a machine without a display.
"""
from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np

from app import config
from app.face_engine import FaceEngine, FaceResult, QualityError, check_quality, decode_image, pick_face
from app.matching import match
from app.smoothing import EmbeddingSmoother
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
    det_score: float = 0.0       # measurements the quality gates look at
    size_px: int = 0
    sharpness: float = 0.0
    turn: float | None = None
    threshold: float = config.MATCH_THRESHOLD  # the threshold actually used for this decision
    embedding: np.ndarray | None = field(default=None, repr=False)
    n_avg: int = 1               # how many frames the score is averaged over (1 = a single frame)

    @property
    def label(self) -> str:
        if not self.usable:
            return f"skipped: {explain_gate(self)}"
        avg = f" (avg of {self.n_avg})" if self.n_avg > 1 else ""
        return f"{self.name} {pct(self.score)}{avg}" if self.matched else f"unknown ({self.reason}, best {pct(self.score)}){avg}"


def pct(cosine: float) -> str:
    """Cosine similarity shown as a percentage. It is a similarity score, NOT a probability of being right."""
    return f"{max(cosine, 0.0) * 100:.0f}%"


def explain_gate(r: "FaceReport") -> str:
    """Which quality gate rejected the frame, with the measured value against the limit (same order as check_quality)."""
    if r.det_score < config.ID_MIN_DET_SCORE:
        return f"unclear: detector confidence {r.det_score:.2f} < {config.ID_MIN_DET_SCORE:.2f} (more light, face the camera)"
    if r.size_px < config.ID_MIN_FACE_PX:
        return f"too small: face {r.size_px}px < {config.ID_MIN_FACE_PX}px (move closer)"
    if r.sharpness < config.ID_MIN_SHARPNESS:
        return f"blurry: sharpness {r.sharpness:.0f} < {config.ID_MIN_SHARPNESS:.0f} (hold still, clean the lens)"
    return r.message or "quality gate"


def short_gate(r: "FaceReport") -> str:
    return explain_gate(r).split(":")[0]


def describe(r: "FaceReport") -> str:
    """One line with every number, for --debug."""
    turn = "n/a" if r.turn is None else f"{r.turn:+.2f}"
    head = (f"face {r.size_px}px (min {config.ID_MIN_FACE_PX}) | detector {r.det_score:.2f} (min {config.ID_MIN_DET_SCORE:.2f}) | "
            f"sharpness {r.sharpness:.0f} (min {config.ID_MIN_SHARPNESS:.0f}) | turn {turn}")
    if not r.usable:
        return head + f" -> SKIPPED, {short_gate(r)}"
    return head + f" -> {r.label}  [need {pct(r.threshold)} to match]"


def ranking(emb: np.ndarray, owners: list[str], gallery: np.ndarray) -> list[tuple[str, float]]:
    best: dict[str, float] = {}
    for o, s in zip(owners, gallery @ emb):
        best[o] = max(best.get(o, -1.0), float(s))
    return sorted(best.items(), key=lambda kv: kv[1], reverse=True)


def report_for(face: FaceResult, owners, gallery, threshold, margin) -> FaceReport:
    m = dict(det_score=face.det_score, size_px=min(face.box[2] - face.box[0], face.box[3] - face.box[1]),
             sharpness=face.sharpness, turn=face.turn, threshold=threshold)
    try:
        check_quality(face, identification=True)
    except QualityError as e:
        return FaceReport(face.box, False, str(e), **m)
    r = match(face.embedding, owners, gallery, threshold=threshold, margin=margin)
    return FaceReport(face.box, True, "", r.matched, r.user_id, r.score, r.reason,
                      ranking(face.embedding, owners, gallery)[:3] if len(owners) else [], embedding=face.embedding, **m)


def identify_frame(engine: FaceEngine, store: FaceStore, img: np.ndarray,
                   threshold: float, margin: float) -> list[FaceReport]:
    owners, gallery = store.all_embeddings()
    return [report_for(f, owners, gallery, threshold, margin) for f in engine.analyse(img)]


def apply_smoothing(reports: list["FaceReport"], smoother: EmbeddingSmoother, store: FaceStore,
                    threshold: float, margin: float) -> list["FaceReport"]:
    """Replace the main (largest usable) face's single-frame result by the average of its last few frames."""
    usable = [r for r in reports if r.usable and r.embedding is not None]
    if not usable:
        return reports
    main = max(usable, key=lambda r: (r.box[2] - r.box[0]) * (r.box[3] - r.box[1]))
    mean, n = smoother.add(main.embedding)
    if n < 2:
        return reports
    owners, gal = store.all_embeddings()
    m = match(mean, owners, gal, threshold=threshold, margin=margin)
    smoothed = replace(main, matched=m.matched, name=m.user_id, score=m.score, reason=m.reason, n_avg=n,
                       ranking=ranking(mean, owners, gal)[:3] if len(owners) else [])
    return [smoothed if r is main else r for r in reports]


def annotate(img: np.ndarray, reports: list[FaceReport], debug: bool = False) -> np.ndarray:
    import cv2

    out = img.copy()
    for r in reports:
        x1, y1, x2, y2 = r.box
        colour = (0, 180, 0) if r.matched else (0, 140, 255) if r.usable else (128, 128, 128)
        cv2.rectangle(out, (x1, y1), (x2, y2), colour, 2)
        short = (f"{r.name} {pct(r.score)}" if r.matched else f"unknown {pct(r.score)}") if r.usable else f"skipped: {short_gate(r)}"
        cv2.putText(out, short, (x1, max(y1 - 8, 14)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, colour, 2)
    if debug:
        h = out.shape[0]
        for i, r in enumerate(reports[:3]):
            cv2.putText(out, describe(r), (8, h - 12 - 18 * (len(reports[:3]) - 1 - i)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
        if not reports:
            cv2.putText(out, "no face detected", (8, h - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    return out


def apply_gate_overrides(a) -> None:
    """Let the user relax the quality gates (a laptop webcam is often softer than test photos)."""
    for arg, names in (("min_sharpness", ("MIN_SHARPNESS", "ID_MIN_SHARPNESS")), ("min_face", ("MIN_FACE_PX", "ID_MIN_FACE_PX")),
                       ("min_det", ("MIN_DET_SCORE", "ID_MIN_DET_SCORE"))):
        value = getattr(a, arg, None)
        if value is not None:
            for name in names:
                setattr(config, name, value)


def list_images(paths: list[str]) -> list[Path]:
    found: list[Path] = []
    for p in (Path(x).expanduser() for x in paths):
        if not p.exists():
            raise SystemExit(f"Cannot find '{p}'. Check the path (tip: drag the file or folder into this window to paste its real path).")
        found += sorted(f for f in p.rglob("*") if f.suffix.lower() in IMAGE_EXT) if p.is_dir() else [p]
    return found


def largest_usable(engine: FaceEngine, img: np.ndarray, identification: bool = False) -> FaceResult:
    face = pick_face(engine.analyse(img))  # raises QualityError("No face found...")
    check_quality(face, identification=identification)
    return face


# ---------------------------------------------------------------- commands
def face_from_camera(engine, camera: str, seconds: float = 10.0, frames: int = 5, warmup: float = 1.0) -> FaceResult:
    """A representative face from the camera: ignore the first `warmup` seconds (a Mac camera's first frames are often dark or
    out of focus while auto-exposure settles), then average the templates of up to `frames` usable frames, like live mode does.
    Raises QualityError with the last reason if no usable frame shows up within `seconds`."""
    cam, last, good = open_camera(camera), "No face found. Look at the camera.", []
    try:
        t0 = time.time()
        while time.time() - t0 < seconds and len(good) < frames:
            frame = grab(cam, camera.isdigit(), timeout=3.0)
            if frame is None:
                break
            if time.time() - t0 < warmup:
                continue
            try:
                good.append(largest_usable(engine, frame, identification=True))
            except QualityError as e:
                last = str(e)
    finally:
        cam.release()
    if not good:
        raise QualityError(last)
    mean = np.mean([f.embedding for f in good], axis=0)
    return replace(good[-1], embedding=(mean / np.linalg.norm(mean)).astype(np.float32))


def cmd_enroll(a, engine, store) -> int:
    name = a.name
    exists = store.user_exists(name)
    if a.add and not exists:
        print(f"'{name}' is not saved yet; run enroll without --add first.", file=sys.stderr)
        return 1
    if exists and not a.add:
        print(f"'{name}' is already saved. To add webcam templates to the same person use `enroll --name {name} --add` "
              f"(do NOT enroll the same person under a second name: two similar names are rejected as ambiguous). "
              f"To start over run `delete --name {name}`.", file=sys.stderr)
        return 1
    embs: list[np.ndarray] = []
    if a.add:  # check BEFORE capturing, so a refused add never wastes a capture session
        room = store.room_for(name, a.max_templates)
        need = GUIDED_TOTAL if a.guided else config.MIN_ENROLL_FRAMES
        if room < need:
            print(f"'{name}' already has {a.max_templates - room} templates and the limit is {a.max_templates}, so there is room for "
                  f"{room} more but this needs {need}. Raise the limit with --max-templates, or start over with `delete --name {name}`.",
                  file=sys.stderr)
            return 1
    if a.images:
        for p in list_images(a.images):
            try:
                embs.append(largest_usable(engine, decode_image(p.read_bytes())).embedding)
            except QualityError as e:
                print(f"  skip {p.name}: {e}")
    elif a.guided:
        embs = capture_guided(a, engine)
    else:
        embs = capture_from_camera(a, engine)
    if len(embs) < config.MIN_ENROLL_FRAMES:
        print(f"Only {len(embs)} usable frame(s); need {config.MIN_ENROLL_FRAMES}. Nothing saved.", file=sys.stderr)
        return 1
    embs = embs[: (GUIDED_TOTAL if a.guided else config.MAX_ENROLL_FRAMES)]
    if a.add:
        try:
            total = store.add_embeddings(name, embs, a.max_templates)
        except ValueError as e:
            print(e, file=sys.stderr)
            return 1
        print(f"Added {len(embs)} templates to '{name}' (now {total}) -> {a.db}")
        return 0
    store.add_user(name, PLACEHOLDER_WALLET, embs)
    print(f"Saved '{name}' with {len(embs)} face templates -> {a.db}")
    return 0


PROMPTS = ["Look straight at the camera", "Turn slightly left", "Turn slightly right",
           "Lift your chin a little", "Look straight again", "Tilt your head slightly", "Smile", "Neutral face"]


# Guided enrollment: cover the conditions you will really stand in (distance, light), not only head poses.
GUIDED_STEPS = [
    ("Look straight at the camera, about an arm's length away", 2),
    ("Turn your head slightly left", 1),
    ("Turn your head slightly right", 1),
    ("Lift your chin a little", 1),
    ("Lean in close so your face fills most of the picture", 2),
    ("Sit back about 1.5 metres from the camera", 2),
    ("Make the room dimmer, or turn so the light is behind you", 2),
    ("Light from one side only (a window or a lamp)", 2),
]
GUIDED_TOTAL = sum(n for _, n in GUIDED_STEPS)


class GuidedPlan:
    """Steps through GUIDED_STEPS: show each instruction for `lead` seconds so the person can get into position, then collect
    that step's good frames; give up on a step after `timeout` seconds so one impossible step cannot block the rest."""

    def __init__(self, steps=GUIDED_STEPS, lead: float = 4.0, timeout: float = 12.0, clock=time.monotonic):
        self.steps, self.lead, self.timeout, self._clock = steps, lead, timeout, clock
        self.index, self.got, self._started = 0, 0, clock()

    @property
    def done(self) -> bool:
        return self.index >= len(self.steps)

    @property
    def instruction(self) -> str:
        return self.steps[self.index][0] if not self.done else ""

    def collecting(self) -> bool:
        """True once the person has had `lead` seconds to get into position."""
        self._maybe_skip()
        return not self.done and self._clock() - self._started >= self.lead

    def countdown(self) -> int:
        return max(0, int(self.lead - (self._clock() - self._started) + 0.999))

    def got_frame(self) -> None:
        self.got += 1
        if self.got >= self.steps[self.index][1]:
            self._advance()

    def _maybe_skip(self) -> None:
        if not self.done and self._clock() - self._started > self.lead + self.timeout:
            self._advance()

    def _advance(self) -> None:
        self.index, self.got, self._started = self.index + 1, 0, self._clock()

    def status(self) -> str:
        if self.done:
            return "done"
        head = f"Step {self.index + 1}/{len(self.steps)}: {self.instruction}"
        return head + (f"  (starting in {self.countdown()}s)" if not self.collecting() else f"  (capturing {self.got}/{self.steps[self.index][1]})")


def capture_guided(a, engine) -> list[np.ndarray]:
    import cv2

    cam, got, last, plan, shown = open_camera(a.camera), [], 0.0, GuidedPlan(lead=a.lead), -1
    print(f"Guided enrollment: {len(GUIDED_STEPS)} short steps, about {GUIDED_TOTAL} frames. Move as each instruction says. Press q to stop.", flush=True)
    while not plan.done:
        frame = grab(cam, a.camera.isdigit())
        if frame is None:
            break
        if plan.index != shown:
            shown = plan.index
            print(f"  {plan.status().split('  (')[0]}", flush=True)
        msg = plan.status()
        if plan.collecting():
            try:
                face = largest_usable(engine, frame)
                if time.time() - last >= a.interval:
                    got.append(face.embedding)
                    last = time.time()
                    plan.got_frame()
            except QualityError as e:
                msg += f"  - {e}"
        view = frame.copy()
        cv2.putText(view, msg[:90], (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 0), 2)
        if show("guided enroll (q = stop)", view, a.no_window):
            break
    cam.release()
    if not a.no_window:
        cv2.destroyAllWindows()
    return got


def open_camera(src: str):
    import cv2

    cam = cv2.VideoCapture(int(src) if src.isdigit() else src)
    if not cam.isOpened():
        raise SystemExit(f"Cannot open camera '{src}'. On macOS allow camera access for your terminal "
                         "(System Settings > Privacy & Security > Camera); try --camera 1 if 0 is your phone.")
    return cam


def grab(cam, is_device: bool, timeout: float = 6.0):
    """Next frame. A camera that is slow to start is retried for `timeout` seconds (the first reads often fail on a Mac);
    a video file used as a test camera loops. None means give up."""
    import cv2

    t0 = time.time()
    while time.time() - t0 < timeout:
        ok, frame = cam.read()
        if ok:
            return frame
        if is_device:
            time.sleep(0.05)
        else:
            cam.set(cv2.CAP_PROP_POS_FRAMES, 0)
    return None


def show(window: str, frame, no_window: bool) -> bool:
    """Returns True if the user pressed q."""
    if no_window:
        return False
    import cv2

    try:
        cv2.imshow(window, frame)
        if not getattr(show, "_front", False):
            show._front = True
            try:
                cv2.setWindowProperty(window, cv2.WND_PROP_TOPMOST, 1)  # not every OpenCV build supports this
            except cv2.error:
                pass
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
        frame = grab(cam, a.camera.isdigit())
        if frame is None:
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
    is_device = a.camera.isdigit()
    last_line, last_print_t, got_frame, failures, why = "", 0.0, False, 0, "stopped"
    smoother = EmbeddingSmoother(size=a.smooth)
    print(f"Camera {a.camera} opened. Waiting for frames (the first ones can take a few seconds on a Mac)...", flush=True)
    try:
        while True:
            ok, frame = cam.read()
            if not ok:
                if not is_device:
                    cam.set(1, 0)  # loop a video file
                    continue
                failures += 1
                if failures > 60:  # about 6 seconds of nothing
                    why = "the camera stopped delivering frames (check Terminal's camera permission and that no other app uses it)"
                    break
                time.sleep(0.1)
                continue
            failures = 0
            if not got_frame:
                got_frame = True
                print("Camera is delivering frames." + ("" if a.no_window else
                      " A window called 'identify (q = quit)' should be open. If you cannot see it, look behind your other "
                      "windows, or stop (Ctrl+C) and rerun with --no-window --debug for text output."), flush=True)
            n += 1
            if n % a.every == 0:
                reports = identify_frame(engine, store, frame, a.threshold, a.margin)
                reports = apply_smoothing(reports, smoother, store, a.threshold, a.margin) if a.smooth > 1 else reports
                line = " | ".join(describe(r) if a.debug else r.label for r in reports) or "no face detected"
                now = time.time()
                # print in every mode, at most about twice a second, so the terminal never looks stuck
                if (line != last_line and now - last_print_t > 0.5) or (a.debug and now - last_print_t > 1.0):
                    print(line, flush=True)
                    last_print_t = now
                last_line = line
            if show("identify (q = quit)", annotate(frame, reports, a.debug), a.no_window):
                why = "q pressed"
                break
            if a.max_seconds and time.time() - t0 > a.max_seconds:
                why = "time limit reached"
                break
    except KeyboardInterrupt:
        why = "Ctrl+C"
    finally:
        cam.release()
    print(f"Stopped: {why}.", flush=True)
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
                face = largest_usable(engine, decode_image(p.read_bytes()), identification=True)
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


def decide_from_ranking(ranked: list[tuple[str, float]], threshold: float, margin: float) -> str | None:
    """The same rule as app.matching.match, for a ranked list of (person, best score): recognised only if the best person
    clears the threshold AND beats the runner-up by the margin."""
    if not ranked or ranked[0][1] < threshold:
        return None
    if len(ranked) > 1 and ranked[0][1] - ranked[1][1] < margin:
        return None
    return ranked[0][0]


def cmd_selftest(a, engine, store) -> int:
    """Guided test: each person steps up in turn, is looked up, and is marked PASS or FAIL against who was meant to be there."""
    people = [n.strip() for n in a.names.split(",")] if a.names else sorted(set(store.all_embeddings()[0]))
    if not people:
        print("Nobody is enrolled yet. Run `databricks_sync pull --refresh` or `enroll` first.", file=sys.stderr)
        return 1
    steps = [(p, p) for _ in range(a.rounds) for p in people] + ([("someone who is NOT enrolled", None)] if a.outsider else [])
    if a.databricks:
        from app.databricks_store import DatabricksFaces

        dbx = DatabricksFaces()
        lookup = lambda emb: dbx.search(emb, 3)
        print("Looking people up with Databricks Vector Search.")
    else:
        owners, gal = store.all_embeddings()
        lookup = lambda emb: ranking(emb, owners, gal)[:3]
        print("Looking people up with the local templates.")
    rows = []
    for who, expected in steps:
        input(f"\nNext: {who}. Stand at the camera, look at it, and press Enter... ")
        try:
            face = face_from_camera(engine, a.camera)
        except QualityError as e:
            print(f"  no usable photo: {e}")
            rows.append((who, expected, None, None, 0.0, None, 0.0))
            continue
        ranked = lookup(face.embedding)
        top, score = (ranked[0] if ranked else (None, 0.0))
        nxt, nxt_score = (ranked[1] if len(ranked) > 1 else (None, 0.0))
        got = decide_from_ranking(ranked, a.threshold, a.margin)
        ok = got == expected
        shown = f"recognised as {got}" if got else "not recognised"
        print(f"  expected {who:28} -> {shown} (best {top} {pct(score)}; next {nxt} {pct(nxt_score)})   {'PASS' if ok else 'FAIL'}")
        rows.append((who, expected, got, top, score, nxt, nxt_score))
    done = [r for r in rows if r[3] is not None or r[2] is not None]
    passed = sum(1 for r in rows if r[2] == r[1] and r[3] is not None)
    right = [r[4] for r in rows if r[1] is not None and r[2] == r[1]]
    wrong = [r[4] for r in rows if (r[1] is None and r[3] is not None) or (r[1] is not None and r[3] not in (None, r[1]))]
    print("\n==== SELFTEST RESULT (paste this) ====")
    print(f"passed {passed} of {len(rows)} steps   threshold {pct(a.threshold)}   skipped (no photo): {len(rows) - len(done)}")
    if right:
        print(f"right person recognised: {len(right)}   lowest score {pct(min(right))}   median {pct(float(np.median(right)))}")
    if wrong:
        print(f"wrong-person / outsider best scores: highest {pct(max(wrong))}")
    for who, expected, got, top, score, nxt, nxt_score in rows:
        print(f"  {who:28} expected {str(expected):10} got {str(got):10} best {top} {pct(score)}  next {nxt} {pct(nxt_score)}")
    return 0 if passed == len(rows) else 2


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
    ap.add_argument("--min-sharpness", type=float, help=f"override the blur gate for this run (identification default {config.ID_MIN_SHARPNESS:g}, enrollment {config.MIN_SHARPNESS:g})")
    ap.add_argument("--min-face", type=int, help=f"smallest face in pixels (identification default {config.ID_MIN_FACE_PX}, enrollment {config.MIN_FACE_PX})")
    ap.add_argument("--min-det", type=float, help=f"detector confidence gate (identification default {config.ID_MIN_DET_SCORE}, enrollment {config.MIN_DET_SCORE})")
    sub = ap.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("enroll"); e.add_argument("--name", required=True)
    e.add_argument("--images", nargs="+"); e.add_argument("--count", type=int, default=3)
    e.add_argument("--camera", default="0"); e.add_argument("--interval", type=float, default=1.0)
    e.add_argument("--guided", action="store_true", help="step-by-step prompts that also vary distance and lighting (best for robust scores)")
    e.add_argument("--lead", type=float, default=4.0, help="seconds to get into position at each guided step")
    e.add_argument("--max-templates", type=int, default=40, help="most templates one person may hold (default 40)")
    e.add_argument("--add", action="store_true", help="add templates to a person who is already saved (best way to improve scores)")
    e.add_argument("--no-window", action="store_true"); e.set_defaults(fn=cmd_enroll)

    i = sub.add_parser("identify"); i.add_argument("--image", nargs="+"); i.add_argument("--webcam", action="store_true")
    i.add_argument("--camera", default="0"); i.add_argument("--every", type=int, default=2)
    i.add_argument("--annotate", metavar="DIR"); i.add_argument("--no-window", action="store_true")
    i.add_argument("--max-seconds", type=float, default=0)
    i.add_argument("--smooth", type=int, default=5, help="average the main face over its last N good frames (1 = off); steadier than one frame")
    i.add_argument("--debug", action="store_true", help="show every measurement (face size, detector, sharpness, score)")
    i.set_defaults(fn=cmd_identify)

    v = sub.add_parser("evaluate"); v.add_argument("--name", required=True)
    v.add_argument("--mine", nargs="+"); v.add_argument("--others", nargs="+"); v.set_defaults(fn=cmd_evaluate)

    t = sub.add_parser("selftest", help="guided test: each person steps up and is marked PASS or FAIL")
    t.add_argument("--names", help="comma-separated people to test (default: everyone enrolled)")
    t.add_argument("--rounds", type=int, default=1, help="how many times through the list")
    t.add_argument("--outsider", action="store_true", help="add a step for someone who is NOT enrolled (should come back unrecognised)")
    t.add_argument("--databricks", action="store_true", help="look people up with Databricks Vector Search instead of the local templates")
    t.add_argument("--camera", default="0"); t.set_defaults(fn=cmd_selftest)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    d = sub.add_parser("delete"); d.add_argument("--name", required=True); d.set_defaults(fn=cmd_delete)

    a = ap.parse_args(argv)
    apply_gate_overrides(a)
    from app.face_engine import InsightFaceEngine

    if a.cmd not in ("list", "delete"):
        print("Loading the face model (the very first run downloads ~125 MB and can take a minute)...", file=sys.stderr, flush=True)
    engine = None if a.cmd in ("list", "delete") else InsightFaceEngine()
    if engine:
        print("Model ready.", file=sys.stderr, flush=True)
    return a.fn(a, engine, FaceStore(a.db))


if __name__ == "__main__":
    sys.exit(main())
