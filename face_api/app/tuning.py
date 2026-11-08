"""Threshold-tuning maths. Pure functions over embeddings, no camera or model needed.

Data model: per person, an *enroll* set (the gallery, like a real enrollment) and *probe*
embeddings captured later under varied conditions (tagged, e.g. "dim", "glasses", "angle").
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .matching import match


@dataclass
class Probe:
    person: str
    tag: str
    emb: np.ndarray


@dataclass
class Row:
    threshold: float
    frr: float          # own probes NOT identified as the right person (rejected or wrong)
    wrong_user: float   # own probes identified as someone else
    far: float | None   # open-set: probes of a person matched to anyone when they are not enrolled


def _gallery(enroll: dict[str, np.ndarray], skip: str | None = None):
    owners, vecs = [], []
    for person, embs in enroll.items():
        if person == skip:
            continue
        owners += [person] * len(embs)
        vecs.append(embs)
    return owners, (np.concatenate(vecs) if vecs else np.zeros((0, 512), np.float32))


def sweep(enroll: dict[str, np.ndarray], probes: list[Probe], thresholds, margin: float) -> list[Row]:
    full = _gallery(enroll)
    loo = {p: _gallery(enroll, skip=p) for p in enroll}
    rows = []
    for t in thresholds:
        ok = wrong = 0
        far_hits = far_n = 0
        for pr in probes:
            r = match(pr.emb, *full, threshold=t, margin=margin)
            if r.matched and r.user_id == pr.person:
                ok += 1
            elif r.matched:
                wrong += 1
            owners, vecs = loo[pr.person]
            if len(set(owners)) >= 1:
                far_n += 1
                far_hits += match(pr.emb, owners, vecs, threshold=t, margin=margin).matched
        n = len(probes)
        rows.append(Row(round(float(t), 3), 1 - ok / n, wrong / n, far_hits / far_n if far_n else None))
    return rows


def score_stats(enroll: dict[str, np.ndarray], probes: list[Probe]):
    """Genuine = probe vs own best enroll score; impostor = probe vs each other person's best."""
    genuine, impostor = [], []
    per_tag: dict[str, list[float]] = {}
    for pr in probes:
        for person, embs in enroll.items():
            s = float((embs @ pr.emb).max())
            if person == pr.person:
                genuine.append(s)
                per_tag.setdefault(pr.tag, []).append(s)
            else:
                impostor.append(s)
    return np.array(genuine), np.array(impostor), per_tag


def recommend(rows: list[Row], max_far: float = 0.01) -> Row | None:
    """Lowest threshold whose open-set FAR is within max_far (lowest = fewest false rejects)."""
    for r in rows:
        if r.far is not None and r.far <= max_far:
            return r
    return None
