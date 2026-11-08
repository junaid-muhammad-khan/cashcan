"""Can a small trained layer on top of the frozen face model beat the pretrained model? Test honestly.

The adapter is  f(e) = normalize(e + W e)  with W starting at 0 (= the pretrained model exactly), trained on
LFW identities with a CosFace margin loss. Rules that keep the answer honest:
  * people-disjoint splits: train / validation / test people never overlap, and strangers are people with a
    single photo, who are never used in training;
  * early stopping and the L2 strength are chosen on validation people only;
  * if no epoch beats the untrained model on validation, the "adapter" stays identity;
  * repeated over several random splits, so one lucky split cannot decide.

  python -m tools.lfw_embed --data DIR --out DIR/emb
  python -m tools.train_adapter --emb DIR/emb --report TRAINING.md [--save adapter.npz]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

from tools.eval_lfw import roc, wilson_upper
from app.matching import match


def load(emb_dir: Path):
    parts = [np.load(f) for f in sorted(emb_dir.glob("chunk_*.npz"))]
    cat = lambda k: np.concatenate([p[k] for p in parts])
    label, status, emb = cat("label"), cat("status"), cat("emb")
    ok = status == 0
    return label[ok], emb[ok].astype(np.float32), int(len(status)), int(ok.sum())


def split_people(label, seed, val_frac=0.15, test_frac=0.25):
    rng = np.random.default_rng(seed)
    uniq, counts = np.unique(label, return_counts=True)
    multi = uniq[counts >= 2]
    singles = uniq[counts == 1]
    multi, singles = rng.permutation(multi), rng.permutation(singles)
    n_test, n_val = int(len(multi) * test_frac), int(len(multi) * val_frac)
    return dict(test=set(multi[:n_test].tolist()), val=set(multi[n_test:n_test + n_val].tolist()),
                train=set(multi[n_test + n_val:].tolist()),
                strangers_val=set(singles[: len(singles) // 3].tolist()),
                strangers_test=set(singles[len(singles) // 3:].tolist()))


def make_pairs(label, people: set, rng, max_same_per_person=20):
    """All same-person pairs (capped per person) + the same number of random different-person pairs."""
    idx_by = {p: np.flatnonzero(label == p) for p in people}
    a, b = [], []
    for p, idx in idx_by.items():
        pairs = [(i, j) for k, i in enumerate(idx) for j in idx[k + 1:]]
        if len(pairs) > max_same_per_person:
            pairs = [pairs[x] for x in rng.choice(len(pairs), max_same_per_person, replace=False)]
        a += [i for i, _ in pairs]; b += [j for _, j in pairs]
    n_same = len(a)
    pool = np.concatenate(list(idx_by.values()))
    da, db = [], []
    while len(da) < n_same:
        i, j = rng.choice(pool, 2, replace=False)
        if label[i] != label[j]:
            da.append(i); db.append(j)
    return np.array(a + da), np.array(b + db), np.array([True] * n_same + [False] * n_same)


def embed_fn(W):
    def f(x):
        z = x if W is None else x + x @ W.T
        return z / np.linalg.norm(z, axis=1, keepdims=True)
    return f


def verif(f, emb, pairs):
    a, b, same = pairs
    s = np.einsum("ij,ij->i", f(emb[a]), f(emb[b]))
    auc, eer, tar1, tar01, _ = roc(s, same)
    return dict(auc=auc, eer=eer, tar1=tar1, tar01=tar01, scores=s, same=same)


def train(emb, label, train_people, val_pairs, lam, margin, seed, epochs=60, patience=8, lr=2e-3):
    import torch
    import torch.nn.functional as F

    torch.manual_seed(seed)
    mask = np.isin(label, list(train_people))
    X, y_raw = torch.tensor(emb[mask]), label[mask]
    classes, y = np.unique(y_raw, return_inverse=True)
    y = torch.tensor(y)
    proxies = torch.nn.Parameter(F.normalize(torch.stack([X[y == c].mean(0) for c in range(len(classes))]), dim=1).clone())
    W = torch.nn.Parameter(torch.zeros(512, 512))
    opt = torch.optim.Adam([W, proxies], lr=lr)
    best_W, best_eer, bad = np.zeros((512, 512), np.float32), verif(embed_fn(None), emb, val_pairs)["eer"], 0
    base_eer = best_eer
    for ep in range(epochs):
        perm = torch.randperm(len(X))
        for i in range(0, len(X), 256):
            idx = perm[i:i + 256]
            z = F.normalize(X[idx] + X[idx] @ W.T, dim=1)
            cos = z @ F.normalize(proxies, dim=1).T
            logits = 30.0 * (cos - margin * F.one_hot(y[idx], len(classes)))
            loss = F.cross_entropy(logits, y[idx]) + lam * (W ** 2).sum()
            opt.zero_grad(); loss.backward(); opt.step()
        eer = verif(embed_fn(W.detach().numpy()), emb, val_pairs)["eer"]
        if eer < best_eer - 1e-6:
            best_eer, best_W, bad = eer, W.detach().numpy().copy(), 0
        else:
            bad += 1
            if bad >= patience:
                break
    return best_W, base_eer, best_eer, ep + 1


def identification(f, emb, label, test_people, strangers, thresholds, margin, rng, max_probes=8):
    enrolled = [p for p in sorted(test_people) if (label == p).sum() >= 5]
    owners, gal, probes = [], [], []
    for p in enrolled:
        idx = rng.permutation(np.flatnonzero(label == p))
        for j in idx[:3]:
            owners.append(p); gal.append(emb[j])
        probes += [(p, emb[j]) for j in idx[3:3 + max_probes]]
    g = f(np.stack(gal))
    pe = f(np.stack([e for _, e in probes]))
    sidx = np.flatnonzero(np.isin(label, list(strangers)))
    se = f(emb[sidx])
    rows = []
    for t in thresholds:
        ok = wrong = 0
        for (p, _), e in zip(probes, pe):
            r = match(e, owners, g, threshold=t, margin=margin)
            ok += r.matched and r.user_id == p
            wrong += r.matched and r.user_id != p
        fa = sum(match(e, owners, g, threshold=t, margin=margin).matched for e in se)
        rows.append((t, ok / len(probes), wrong / len(probes), fa, len(se)))
    return len(enrolled), len(probes), rows


def paired_bootstrap(sc0, sc1, same, n=300, seed=0):
    rng = np.random.default_rng(seed)
    d = []
    for _ in range(n):
        i = rng.integers(0, len(same), len(same))
        if same[i].all() or (~same[i]).all():
            continue
        d.append(roc(sc0[i], same[i])[1] - roc(sc1[i], same[i])[1])  # baseline EER - adapter EER (>0 = adapter better)
    return np.percentile(d, [2.5, 97.5])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--emb", required=True)
    ap.add_argument("--report", default="TRAINING.md")
    ap.add_argument("--save")
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--margin", type=float, default=0.05, help="ambiguity margin used by match()")
    a = ap.parse_args(argv)
    label, emb, n_all, n_ok = load(Path(a.emb))
    uniq, counts = np.unique(label, return_counts=True)
    out = ["# Does training an adapter on LFW help?\n"]
    w = out.append
    w(f"{n_ok} of {n_all} LFW images passed the quality gates; {len(uniq)} people, {int((counts >= 2).sum())} with 2+ photos "
      f"({int(counts[counts >= 2].sum())} images), {int((counts == 1).sum())} with a single photo (used only as strangers).\n")
    w("Adapter: `f(e) = normalize(e + W e)`, W starts at 0 (= the pretrained model), CosFace loss on train people. "
      "Train / validation / test **people are disjoint**; early stopping and the L2 strength use validation only; "
      "if nothing beats the untrained model on validation, the adapter stays identity.\n")
    thresholds = [0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60]
    runs = []
    for seed in range(a.seeds):
        sp = split_people(label, seed)
        rng = np.random.default_rng(100 + seed)
        val_pairs, test_pairs = make_pairs(label, sp["val"], rng), make_pairs(label, sp["test"], rng)
        best = None
        for lam in (0.0, 1e-3, 1e-2, 1e-1):
            W, base_eer, eer, epochs = train(emb, label, sp["train"], val_pairs, lam, 0.2, seed)
            if best is None or eer < best[2]:
                best = (lam, W, eer, base_eer, epochs)
        lam, W, val_eer, val_base, epochs = best
        f0, f1 = embed_fn(None), embed_fn(W)
        v0, v1 = verif(f0, emb, test_pairs), verif(f1, emb, test_pairs)
        ci = paired_bootstrap(v0["scores"], v1["scores"], v0["same"], seed=seed)
        id0 = identification(f0, emb, label, sp["test"], sp["strangers_test"], thresholds, a.margin, np.random.default_rng(seed))
        id1 = identification(f1, emb, label, sp["test"], sp["strangers_test"], thresholds, a.margin, np.random.default_rng(seed))
        runs.append(dict(seed=seed, lam=lam, epochs=epochs, val_base=val_base, val_ad=val_eer, v0=v0, v1=v1, ci=ci,
                         id0=id0, id1=id1, n_pairs=len(test_pairs[2]), W=W, split=sp))
        print(f"seed {seed}: lam={lam} epochs={epochs} val EER {val_base:.2%}->{val_eer:.2%}  "
              f"test EER {v0['eer']:.2%}->{v1['eer']:.2%}", file=sys.stderr, flush=True)

    w("## Verification on held-out people (test pairs)\n")
    w("| Split | train people | test pairs | chosen L2 | epochs | Val EER base -> adapter | **Test EER base -> adapter** | 95% CI of improvement | Test TAR@1%FAR base -> adapter | Test TAR@0.1%FAR base -> adapter |\n|---|---|---|---|---|---|---|---|---|---|")
    for r in runs:
        w(f"| {r['seed']} | {len(r['split']['train'])} | {r['n_pairs']} | {r['lam']:g} | {r['epochs']} | "
          f"{r['val_base']:.2%} -> {r['val_ad']:.2%} | **{r['v0']['eer']:.2%} -> {r['v1']['eer']:.2%}** | "
          f"[{r['ci'][0] * 100:+.2f}, {r['ci'][1] * 100:+.2f}] pts | {r['v0']['tar1']:.2%} -> {r['v1']['tar1']:.2%} | "
          f"{r['v0']['tar01']:.2%} -> {r['v1']['tar01']:.2%} |")
    d_eer = np.array([r["v0"]["eer"] - r["v1"]["eer"] for r in runs])
    w(f"\nMean EER improvement over {len(runs)} splits: **{d_eer.mean() * 100:+.2f} points** (min {d_eer.min() * 100:+.2f}, max {d_eer.max() * 100:+.2f}). "
      "Positive = adapter better. A CI containing 0 means the difference is not distinguishable from noise.\n")

    w("## Identification on held-out people (seed 0, enroll 3 photos each)\n")
    r = runs[0]
    n_people, n_probes, _ = r["id0"]
    w(f"{n_people} test people, {n_probes} probes, {r['id0'][2][0][4]} stranger photos (people with one photo, never trained on).\n")
    w("| Threshold | Recognised base -> adapter | Wrong name base -> adapter | Strangers accepted base -> adapter |\n|---|---|---|---|")
    for row0, row1 in zip(r["id0"][2], r["id1"][2]):
        w(f"| {row0[0]:.2f} | {row0[1]:.1%} -> {row1[1]:.1%} | {row0[2]:.2%} -> {row1[2]:.2%} | "
          f"{row0[3]}/{row0[4]} -> {row1[3]}/{row1[4]} |")
    w("\n## Reading this\n")
    w("- Same train/validation/test people for both columns; the untrained model is the baseline, not a straw man.\n"
      "- This measures LFW press photos only. Whatever the table shows, it says nothing certain about your bin's webcam.\n"
      "- The backbone (WebFace600K) may have seen some LFW people while pretraining; I cannot rule that out, but it applies equally to both columns.\n")
    Path(a.report).write_text("\n".join(out) + "\n")
    print("\n".join(out))
    if a.save:
        np.savez(a.save, W=runs[0]["W"], lam=runs[0]["lam"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
