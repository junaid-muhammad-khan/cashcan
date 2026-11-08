"""Measure the real pipeline's accuracy on LFW (Labeled Faces in the Wild).

Runs the same steps the bin runs: detect -> quality gates -> ArcFace embedding -> match() with the
configured threshold and ambiguity margin. Three questions:
  1. Verification: given two photos, same person or not? (pairs split)
  2. Identification: enroll 3 photos each for N people, then look up held-out photos of those people
     (should be recognised) and photos of people who are NOT enrolled (should be rejected).
  3. Is the liveness head-turn measure sane on real faces? (vs InsightFace's own yaw estimate)

  pip install -r requirements-eval.txt
  python -m tools.eval_lfw --data DIR --report EVAL.md      # DIR has data.parquet + pairs_test.parquet
                                                            # (huggingface.co/datasets/logasja/lfw)
Embeddings are cached (--cache), so re-running the analysis is instant.
LFW is celebrity press photos, not webcam shots at a bin: treat it as a floor on how the model behaves
on real faces, not as the accuracy you will see on stage. Use tools.tune for that.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

from app import config
from app.face_engine import FaceResult, QualityError, check_quality, decode_image, pick_face
from app.matching import match

REASONS = {0: "ok", 1: "no face detected", 2: "low detector confidence", 3: "face too small",
           4: "too blurry", 5: "unreadable image"}


def classify(engine, data: bytes):
    """-> (strict status, embedding, turn, yaw, identification status). The strict tier is what enrollment photos must pass; the
    lenient identification tier is what photos that are only looked up must pass (same split the API uses)."""
    try:
        face = pick_face(engine.analyse(decode_image(data)))
    except QualityError as e:
        code = 5 if "read" in str(e) else 1
        return code, None, None, None, code

    def status(identification):
        try:
            check_quality(face, identification=identification)
            return 0
        except QualityError as e:
            m = str(e)
            return 2 if "clear enough" in m else 3 if "closer" in m else 4

    return status(False), face.embedding, face.turn, face.yaw, status(True)


def extract(engine, blobs, label, every=250):
    n = len(blobs)
    st, emb = np.zeros(n, np.int8), np.zeros((n, 512), np.float32)
    st_id = np.zeros(n, np.int8)
    turn, yaw = np.full(n, np.nan, np.float32), np.full(n, np.nan, np.float32)
    t0 = time.time()
    for i, b in enumerate(blobs):
        s, e, tr, yw, sid = classify(engine, b)
        st[i], st_id[i] = s, sid
        if e is not None:
            emb[i], turn[i], yaw[i] = e, tr, (np.nan if yw is None else yw)
        if (i + 1) % every == 0:
            r = (i + 1) / (time.time() - t0)
            print(f"  {label}: {i + 1}/{n}  {r:.1f} img/s  eta {(n - i - 1) / r / 60:.1f} min", file=sys.stderr, flush=True)
    return st, emb, turn, yaw, st_id


# ------------------------------------------------------------------ stats helpers
def wilson_upper(k: int, n: int, z: float = 1.96) -> float:
    if n == 0:
        return float("nan")
    p = k / n
    d = 1 + z * z / n
    return float((p + z * z / (2 * n) + z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / d)


def roc(scores: np.ndarray, same: np.ndarray):
    """AUC, EER, and TAR at fixed FARs. scores higher = more likely same."""
    pos, neg = np.sort(scores[same]), np.sort(scores[~same])
    thr = np.unique(scores)
    tar = 1 - np.searchsorted(pos, thr, "left") / len(pos)
    far = 1 - np.searchsorted(neg, thr, "left") / len(neg)
    auc = float(np.mean(pos[:, None] > neg[None, :]) + 0.5 * np.mean(pos[:, None] == neg[None, :])) if len(pos) * len(neg) < 5e7 else float("nan")
    i = int(np.argmin(np.abs((1 - tar) - far)))
    eer = float(((1 - tar[i]) + far[i]) / 2)
    def tar_at(f):
        ok = far <= f
        return float(tar[ok].max()) if ok.any() else 0.0
    return auc, eer, tar_at(0.01), tar_at(0.001), float(thr[i])


# ------------------------------------------------------------------ data
def read_pairs(path):
    import pyarrow.parquet as pq

    t = pq.read_table(path).to_pydict()
    return np.array(t["pair"], bool), [d["bytes"] for d in t["img_0"]], [d["bytes"] for d in t["img_1"]]


def read_people(path, n_enroll_people, max_probes, n_unknown_people, per_unknown, seed):
    """Pick people and images deterministically. Returns blobs + per-image (person, role)."""
    import pyarrow.parquet as pq

    labels = np.array(pq.read_table(path, columns=["label"]).column("label").to_pylist())
    rng = np.random.default_rng(seed)
    uniq, counts = np.unique(labels, return_counts=True)
    eligible = uniq[counts >= 5]  # need 3 to enroll + at least 2 probes
    enrolled = set(rng.choice(eligible, size=min(n_enroll_people, len(eligible)), replace=False).tolist())
    others = [u for u in uniq if u not in enrolled]
    unknown = set(rng.choice(others, size=min(n_unknown_people, len(others)), replace=False).tolist())
    picks: dict[int, tuple[int, str]] = {}
    for p in enrolled:
        idx = np.flatnonzero(labels == p)
        for j in idx[: 3 + 3 + max_probes]:  # a few spare images in case enrollment frames fail the gates
            picks[int(j)] = (int(p), "enrolled")
    for p in unknown:
        for j in np.flatnonzero(labels == p)[:per_unknown]:
            picks[int(j)] = (int(p), "unknown")
    want = sorted(picks)
    blobs, seen = [], 0
    wanted = set(want)
    for batch in pq.ParquetFile(path).iter_batches(batch_size=512, columns=["image"]):
        for row, d in enumerate(batch.column("image").to_pylist()):
            if seen + row in wanted:
                blobs.append(d["bytes"])
        seen += batch.num_rows
    return blobs, np.array([picks[j][0] for j in want]), np.array([picks[j][1] for j in want]), np.array(want)


# ------------------------------------------------------------------ analysis
def analyse(c, a) -> str:
    out: list[str] = []
    w = out.append
    w("# Face recognition accuracy (LFW)\n")
    w(f"Pipeline: InsightFace `buffalo_s` (ArcFace) via `app.face_engine`, the same quality gates and `match()` the bin uses. "
      f"Settings: threshold {config.MATCH_THRESHOLD}, ambiguity margin {config.AMBIGUITY_MARGIN}, "
      f"min face {config.MIN_FACE_PX}px, min detector score {config.MIN_DET_SCORE}, min sharpness {config.MIN_SHARPNESS}.\n")

    # ---- gates
    ps = np.concatenate([c["pair_st0"], c["pair_st1"]])
    psi = np.concatenate([c["pair_sti0"], c["pair_sti1"]])
    ids, idi = c["id_st"], c["id_sti"]
    w("## 1. How often a photo is rejected before matching\n")
    w("Two tiers: **enrollment** (strict, because a bad frame would be saved as a template) and **identification** (lenient, because a weak "
      f"frame can only fail to match). Strict: face >= {config.MIN_FACE_PX} px, detector >= {config.MIN_DET_SCORE}, sharpness >= {config.MIN_SHARPNESS:g}. "
      f"Lenient: face >= {config.ID_MIN_FACE_PX} px, detector >= {config.ID_MIN_DET_SCORE}, sharpness >= {config.ID_MIN_SHARPNESS:g}.\n")
    w("| Reason | Pairs images, enrollment tier | Pairs images, identification tier | Identification images, enrollment tier | Identification images, identification tier |\n|---|---|---|---|---|")
    for code, name in REASONS.items():
        w(f"| {name} | {np.mean(ps == code):.1%} | {np.mean(psi == code):.1%} | {np.mean(ids == code):.1%} | {np.mean(idi == code):.1%} |")
    w("\nGallery (enrolled) photos must pass the enrollment tier; every photo that is only looked up needs the identification tier. "
      "Rejected photos are not counted as wrong matches below; at the bin the person is just asked to retry.\n")

    # ---- verification
    same = c["pair_same"]
    good = (c["pair_sti0"] == 0) & (c["pair_sti1"] == 0)
    score = np.einsum("ij,ij->i", c["pair_e0"], c["pair_e1"])
    s, y = score[good], same[good]
    auc, eer, tar1, tar01, eer_thr = roc(s, y)
    acc_cfg = float(np.mean((s >= config.MATCH_THRESHOLD) == y))
    ths = np.arange(0.0, 1.0, 0.005)
    accs = [np.mean((s >= t) == y) for t in ths]
    best = int(np.argmax(accs))
    w("## 2. Verification: are these two photos the same person?\n")
    w(f"{int(good.sum())} usable pairs of {len(same)} ({int(y.sum())} same-person, {int((~y).sum())} different-person).\n")
    w("| Metric | Value |\n|---|---|")
    w(f"| Accuracy at our threshold ({config.MATCH_THRESHOLD}) | **{acc_cfg:.2%}** |")
    w(f"| Best possible accuracy (threshold {ths[best]:.3f}) | {accs[best]:.2%} |")
    w(f"| ROC AUC | {auc:.4f} |")
    w(f"| Equal error rate | {eer:.2%} (at threshold {eer_thr:.2f}) |")
    w(f"| Same-person accepted at 1% false-accept | {tar1:.2%} |")
    w(f"| Same-person accepted at 0.1% false-accept | {tar01:.2%} |")
    w(f"| Mean score: same / different | {s[y].mean():.2f} / {s[~y].mean():.2f} |")
    w("\n(For scale, published ArcFace-class models report about 99.5% on the official 6,000-pair LFW protocol. "
      "This uses the dataset's own pairs split, not the official 10-fold protocol, so treat the comparison as rough.)\n")

    # ---- identification
    person, role, st, emb = c["id_person"], c["id_role"], c["id_st"], c["id_emb"]
    owners, gal, probes = [], [], []
    skipped = 0
    sti = c["id_sti"]
    for p in sorted(set(person[role == "enrolled"].tolist())):
        strict = np.flatnonzero((person == p) & (role == "enrolled") & (st == 0))           # enrollment tier
        if len(strict) < 3:
            skipped += 1
            continue
        for j in strict[:3]:
            owners.append(str(p)); gal.append(emb[j])
        rest = [j for j in np.flatnonzero((person == p) & (role == "enrolled") & (sti == 0)) if j not in set(strict[:3].tolist())]
        if not rest:
            skipped += 1
            owners, gal = owners[:-3], gal[:-3]
            continue
        probes += [(str(p), emb[j]) for j in rest[:a.max_probes]]                            # identification tier
    gal = np.stack(gal)
    unk = [emb[j] for j in np.flatnonzero((role == "unknown") & (sti == 0))]
    n_people = len(set(owners))
    w("## 3. Identification: the bin's real job\n")
    w(f"{n_people} people enrolled with 3 photos each ({skipped} skipped: too few usable photos). "
      f"{len(probes)} later photos of those people must be recognised; "
      f"{len(unk)} photos of {len(set(person[role == 'unknown'].tolist()))} different people who are **not** enrolled must be rejected.\n")
    w("| Threshold | Enrolled person recognised | Wrong person named | Not recognised | Stranger accepted (95% upper bound) |\n|---|---|---|---|---|")
    rows = []
    for t in sorted(set([round(x, 2) for x in np.arange(0.25, 0.71, 0.05)] + [config.MATCH_THRESHOLD])):
        ok = wrong = miss = 0
        for p, e in probes:
            r = match(e, owners, gal, threshold=t, margin=config.AMBIGUITY_MARGIN)
            if r.matched and r.user_id == p: ok += 1
            elif r.matched: wrong += 1
            else: miss += 1
        fa = sum(match(e, owners, gal, threshold=t, margin=config.AMBIGUITY_MARGIN).matched for e in unk)
        n = len(probes)
        rows.append((t, ok / n, wrong / n, miss / n, fa, len(unk)))
        mark = " **(current)**" if abs(t - config.MATCH_THRESHOLD) < 1e-9 else ""
        w(f"| {t:.2f}{mark} | {ok / n:.1%} | {wrong / n:.2%} | {miss / n:.1%} | {fa / len(unk):.2%} ({fa}/{len(unk)}, <= {wilson_upper(fa, len(unk)):.2%}) |")
    w("\nWith 0 strangers accepted out of N, the false-accept rate is still only bounded (about 3/N), not zero.\n")

    # ---- liveness measure validation
    turn, yaw = c["pair_turn"], c["pair_yaw"]
    ok = np.isfinite(turn) & np.isfinite(yaw)
    t_, y_ = turn[ok], yaw[ok]
    w("## 4. Is the liveness head-turn measure sane on real faces?\n")
    w(f"Compared on {int(ok.sum())} real faces against InsightFace's own head-yaw estimate "
      f"(note: yaw sign convention may differ, only magnitude and linearity matter here).\n")
    corr = float(np.corrcoef(np.abs(t_), np.abs(y_))[0, 1])
    w(f"Correlation between |turn ratio| and |yaw|: **{corr:.2f}**\n")
    w("| |yaw| | n | median |turn ratio| | passes 'facing camera' (<= 0.12) | passes 'turned' (>= 0.25) |\n|---|---|---|---|---|")
    edges = [0, 5, 10, 15, 20, 30, 45, 90]
    for lo, hi in zip(edges, edges[1:]):
        m = (np.abs(y_) >= lo) & (np.abs(y_) < hi)
        if m.sum() < 5: continue
        r = np.abs(t_[m])
        w(f"| {lo}-{hi} deg | {int(m.sum())} | {np.median(r):.2f} | {np.mean(r <= config.LIVENESS_CENTER_MAX):.0%} | {np.mean(r >= config.LIVENESS_TURN_MIN):.0%} |")
    w("\nRead: nearly all near-frontal faces should pass 'facing camera' and almost none should pass 'turned'; "
      "faces turned 30+ degrees should mostly pass 'turned'. This checks the measure, not the anti-spoof strength: "
      "LFW has no photo/screen attacks, so spoof resistance is covered only by the unit tests and the geometry argument.\n")

    w("## What this does and does not show\n")
    w("- LFW is celebrity press photos: mostly frontal, decent light, varied age. A bin webcam under venue lighting is harder. Expect worse; measure with `tools.tune` on the team.\n"
      "- Gallery size is 150 people here. Accuracy drops as more people enrol.\n"
      "- No spoofing is in this data, and no demographic breakdown was run: LFW is not balanced, so fairness across groups is **not** measured.\n"
      "- Photos with no detectable face are excluded from accuracy and reported in section 1.\n")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True)
    ap.add_argument("--cache", default="lfw_cache.npz")
    ap.add_argument("--report", default="EVAL.md")
    ap.add_argument("--people", type=int, default=150)
    ap.add_argument("--max-probes", type=int, default=8)
    ap.add_argument("--unknown-people", type=int, default=600)
    ap.add_argument("--unknown-per-person", type=int, default=3)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)
    d = Path(a.data)

    cache = Path(a.cache)
    if cache.exists():
        c = dict(np.load(cache, allow_pickle=False))
        print(f"loaded cache {cache}", file=sys.stderr)
    else:
        from app.face_engine import InsightFaceEngine

        engine = InsightFaceEngine()
        same, b0, b1 = read_pairs(d / "pairs_test.parquet")
        blobs, person, role, rows = read_people(d / "data.parquet", a.people, a.max_probes,
                                                a.unknown_people, a.unknown_per_person, a.seed)
        print(f"pairs: {len(same)}  identification images: {len(blobs)}", file=sys.stderr)
        s0, e0, t0, y0, i0 = extract(engine, b0, "pairs[0]")
        s1, e1, t1, y1, i1 = extract(engine, b1, "pairs[1]")
        si, ei, ti, yi, ii = extract(engine, blobs, "identification")
        c = dict(pair_same=same, pair_st0=s0, pair_st1=s1, pair_sti0=i0, pair_sti1=i1, id_sti=ii, pair_e0=e0, pair_e1=e1,
                 pair_turn=np.concatenate([t0, t1]), pair_yaw=np.concatenate([y0, y1]),
                 id_person=person, id_role=role, id_st=si, id_emb=ei, id_turn=ti, id_yaw=yi)
        np.savez_compressed(cache, **c)
    report = analyse(c, a)
    Path(a.report).write_text(report + "\n")
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
