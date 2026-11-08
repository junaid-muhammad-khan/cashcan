"""How much do distance and lighting hurt recognition, and which fixes help? (simulated on LFW)

Enrolled people are enrolled from CLEAN photos (like a studio-photo enrollment). Their held-out photos and photos of strangers
are then degraded the way a bad bin would be, and looked up with the real pipeline and match(). Fixes are tried on the probe frames:
  CLAHE / auto-gamma / both (lighting), 2x upscale before detection (distance), and a gallery that also holds a dark and a
  small-face template per person (diverse enrollment).

  python -m tools.robustness --data DIR --report ROBUSTNESS.md        # DIR has data.parquet (see tools.eval_lfw)

These are SIMULATED degradations of press photos, not your webcam: they show which fixes matter and roughly how much, then
verify on the real camera with `face_demo identify --webcam --debug`.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

from app import config
from app.face_engine import InsightFaceEngine, QualityError, check_quality, decode_image, pick_face
from app.matching import match
from tools.eval_lfw import read_people


# ---------------------------------------------------------------- degradations (what the camera sees)
def scale(f):
    return lambda im: cv2.resize(im, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)


def gain(g, noise=0.0, seed=0):
    def fn(im):
        out = im.astype(np.float32) * g
        if noise:
            out += np.random.default_rng(seed).normal(0, noise, im.shape)
        return np.clip(out, 0, 255).astype(np.uint8)
    return fn


def side_light(im):  # a window on one side: left bright, right in shadow
    ramp = np.linspace(1.0, 0.15, im.shape[1], dtype=np.float32)[None, :, None]
    return np.clip(im.astype(np.float32) * ramp, 0, 255).astype(np.uint8)


def warm_dim(im):  # tungsten lamp, dim: red up, blue down
    return np.clip(im.astype(np.float32) * np.array([0.6, 0.85, 1.0]) * 0.55, 0, 255).astype(np.uint8)  # BGR


CONDITIONS = {
    "clean": lambda im: im,
    "face ~80 px": scale(0.7), "face ~60 px": scale(0.5), "face ~45 px": scale(0.4), "face ~35 px": scale(0.3),
    "dim (x0.5)": gain(0.5, 3), "dark (x0.25)": gain(0.25, 4), "side light": side_light,
    "over-exposed (x1.8)": gain(1.8), "warm dim lamp": warm_dim,
}


# ---------------------------------------------------------------- candidate fixes (applied to the probe frame)
def clahe(im):
    lab = cv2.cvtColor(im, cv2.COLOR_BGR2LAB)
    lab[:, :, 0] = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(lab[:, :, 0])
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)


def auto_gamma(im, target=110.0):
    mean = float(cv2.cvtColor(im, cv2.COLOR_BGR2GRAY).mean())
    if 80 <= mean <= 170:  # already fine: leave alone
        return im
    g = np.log(target / 255.0) / np.log(max(mean, 1.0) / 255.0)
    lut = (np.linspace(0, 1, 256) ** g * 255).astype(np.uint8)
    return cv2.LUT(im, lut)


FIXES = {"none": lambda im: im, "CLAHE": clahe, "auto-gamma": auto_gamma, "gamma+CLAHE": lambda im: clahe(auto_gamma(im)),
         "upscale 2x": lambda im: cv2.resize(im, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)}


def embed(engine, img):
    """-> (embedding or None, gate status 0 ok/1 no face/2 unclear/3 small/4 blurry)"""
    faces = engine.analyse(img)
    if not faces:
        return None, 1
    f = pick_face(faces)
    try:
        check_quality(f)
        return f.embedding, 0
    except QualityError as e:
        m = str(e)
        return f.embedding, 2 if "clear enough" in m else 3 if "closer" in m else 4


def run(engine, imgs, cond, fix, cache, tag):
    key = (tag, cond, fix)
    if key in cache:
        return cache[key]
    out = []
    for im in imgs:
        d = FIXES[fix](CONDITIONS[cond](im))
        out.append(embed(engine, d))
    cache[key] = out
    print(f"  done {tag} | {cond} | {fix}", file=sys.stderr, flush=True)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True)
    ap.add_argument("--report", default="ROBUSTNESS.md")
    ap.add_argument("--probes", type=int, default=400)
    ap.add_argument("--strangers", type=int, default=400)
    ap.add_argument("--threshold", type=float, default=0.50)
    a = ap.parse_args(argv)
    engine = InsightFaceEngine(modules=["detection", "recognition"])
    blobs, person, role, _ = read_people(Path(a.data) / "data.parquet", 150, 8, 600, 1, 0)
    imgs = [decode_image(b) for b in blobs]
    rng = np.random.default_rng(0)
    cache: dict = {}

    gallery_imgs, owners_idx, probe_imgs, probe_owner, stranger_imgs = [], [], [], [], []
    for p in sorted(set(person[role == "enrolled"].tolist())):
        idx = [i for i in np.flatnonzero((person == p) & (role == "enrolled"))]
        ok = [i for i in idx if embed(engine, imgs[i])[1] == 0]
        if len(ok) < 4:
            continue
        gallery_imgs += [(p, imgs[i]) for i in ok[:3]]
        probe_imgs += [imgs[i] for i in ok[3:3 + 3]]
        probe_owner += [p] * len(ok[3:3 + 3])
    stranger_imgs = [imgs[i] for i in np.flatnonzero(role == "unknown")]
    sel = rng.permutation(len(probe_imgs))[: a.probes]
    probe_imgs, probe_owner = [probe_imgs[i] for i in sel], [probe_owner[i] for i in sel]
    stranger_imgs = [stranger_imgs[i] for i in rng.permutation(len(stranger_imgs))[: a.strangers]]
    owners = [p for p, _ in gallery_imgs]
    gal = np.stack([embed(engine, im)[0] for _, im in gallery_imgs])
    # diverse gallery: per person also one DARK and one SMALL-face template made from their own enrollment photos
    extra_o, extra_e = [], []
    for p in sorted(set(owners)):
        ims = [im for q, im in gallery_imgs if q == p]
        for im, mk in ((ims[0], CONDITIONS["dark (x0.25)"]), (ims[1], CONDITIONS["face ~45 px"])):
            e, st = embed(engine, mk(im))
            if e is not None:
                extra_o.append(p); extra_e.append(e)
    gal_div, owners_div = np.concatenate([gal, np.stack(extra_e)]), owners + extra_o

    def score(cond, fix, diverse=False):
        pe = run(engine, probe_imgs, cond, fix, cache, "probe")
        se = run(engine, stranger_imgs, cond, fix, cache, "stranger")
        G, O = (gal_div, owners_div) if diverse else (gal, owners)
        found = [e is not None for e, _ in pe]
        passed = [st == 0 for _, st in pe]
        rec_gates = rec_all = wrong = 0
        sims = []
        for (e, st), p in zip(pe, probe_owner):
            if e is None:
                continue
            r = match(e, O, G, threshold=a.threshold, margin=config.AMBIGUITY_MARGIN)
            ok = r.matched and r.user_id == p
            rec_all += ok
            rec_gates += ok and st == 0
            wrong += r.matched and r.user_id != p
            sims.append(max(float((G[[i for i, o in enumerate(O) if o == p]] @ e).max()), 0))
        fa = sum(1 for e, _ in se if e is not None and match(e, O, G, threshold=a.threshold, margin=config.AMBIGUITY_MARGIN).matched)
        n, ns = len(pe), len([1 for e, _ in se if e is not None])
        return dict(found=sum(found) / n, passed=sum(passed) / n, rec_gates=rec_gates / n, rec_all=rec_all / n,
                    wrong=wrong / n, fa=fa, ns=ns, sim=float(np.mean(sims)) if sims else 0.0)

    rows = []
    for cond in CONDITIONS:
        rows.append((cond, "none", False, score(cond, "none")))
    for cond in ("dim (x0.5)", "dark (x0.25)", "side light", "over-exposed (x1.8)", "warm dim lamp"):
        for fix in ("CLAHE", "auto-gamma", "gamma+CLAHE"):
            rows.append((cond, fix, False, score(cond, fix)))
    for cond in ("face ~60 px", "face ~45 px", "face ~35 px"):
        rows.append((cond, "upscale 2x", False, score(cond, "upscale 2x")))
    for cond in ("dark (x0.25)", "side light", "face ~60 px", "face ~45 px", "face ~35 px", "warm dim lamp"):
        rows.append((cond, "none", True, score(cond, "none", diverse=True)))

    out = ["# Distance and lighting: how much they hurt, and what helps (simulated on LFW)\n"]
    w = out.append
    w(f"{len(set(owners))} people enrolled from clean photos (3 each); {len(probe_imgs)} held-out photos of them and {len(stranger_imgs)} photos of "
      f"strangers are degraded. Threshold {a.threshold:.0%}, ambiguity margin {config.AMBIGUITY_MARGIN:.0%}. **Simulated degradations of press photos, not a "
      "webcam**: they rank the fixes, then each needs checking on the real camera.\n")
    w("Columns: *face found*; *passes gates* = would not be skipped as too small / blurry / unclear; *recognised (gates on)* = the real bin behaviour "
      "(skipped frames count as not recognised, the person just retries); *recognised (gates off)* = the model alone; *wrong name*; *strangers accepted*; "
      "*mean score* = average similarity of the right person.\n")
    w("| Condition | Fix | Face found | Passes gates | Recognised (gates on) | Recognised (gates off) | Wrong name | Strangers accepted | Mean score |\n|---|---|---|---|---|---|---|---|---|")
    for cond, fix, div, r in rows:
        name = fix + (" + diverse gallery" if div else "")
        w(f"| {cond} | {name} | {r['found']:.0%} | {r['passed']:.0%} | {r['rec_gates']:.0%} | {r['rec_all']:.0%} | {r['wrong']:.1%} | {r['fa']}/{r['ns']} | {r['sim']:.0%} |")
    Path(a.report).write_text("\n".join(out) + "\n")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
