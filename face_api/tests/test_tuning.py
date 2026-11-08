import numpy as np

from app.tuning import Probe, recommend, score_stats, sweep

from .conftest import person_vec


def noisy(pid, scale=0.005, seed=0):
    v = person_vec(pid) + np.random.default_rng(seed).normal(scale=scale, size=512).astype(np.float32)
    return v / np.linalg.norm(v)


def dataset():
    enroll = {f"p{i}": np.stack([noisy(i, seed=10 + j) for j in range(3)]) for i in (1, 2, 3)}
    probes = [Probe(f"p{i}", "dim", noisy(i, scale=0.008, seed=100 + k)) for i in (1, 2, 3) for k in range(4)]
    return enroll, probes


def test_score_stats_separates_genuine_from_impostor():
    gen, imp, per_tag = score_stats(*dataset())
    assert gen.min() > 0.9 and imp.max() < 0.3 and len(per_tag["dim"]) == 12


def test_sweep_low_threshold_accepts_strangers_high_threshold_rejects_own():
    enroll, probes = dataset()
    rows = {r.threshold: r for r in sweep(enroll, probes, [0.0, 0.5, 0.999], margin=0.0)}
    assert rows[0.0].far == 1.0           # accepts everyone
    assert rows[0.5].frr == 0 and rows[0.5].far == 0
    assert rows[0.999].frr == 1.0         # rejects everyone


def test_recommend_picks_lowest_safe_threshold():
    enroll, probes = dataset()
    rows = sweep(enroll, probes, np.arange(0.0, 1.0, 0.1), margin=0.05)
    rec = recommend(rows)
    assert rec is not None and rec.far == 0 and rec.frr == 0
    assert rec.threshold == min(r.threshold for r in rows if r.far == 0)
