"""Pure matching logic: best cosine score per user, with a threshold and an ambiguity check."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import config


@dataclass
class MatchResult:
    matched: bool
    user_id: str | None
    score: float
    reason: str


def match(query: np.ndarray, owners: list[str], gallery: np.ndarray) -> MatchResult:
    if len(owners) == 0:
        return MatchResult(False, None, 0.0, "no_enrolled_users")
    sims = gallery @ query  # both L2-normalised -> cosine similarity
    best: dict[str, float] = {}
    for owner, s in zip(owners, sims):
        best[owner] = max(best.get(owner, -1.0), float(s))
    ranked = sorted(best.items(), key=lambda kv: kv[1], reverse=True)
    top_user, top_score = ranked[0]
    if top_score < config.MATCH_THRESHOLD:
        return MatchResult(False, None, top_score, "below_threshold")
    if len(ranked) > 1 and top_score - ranked[1][1] < config.AMBIGUITY_MARGIN:
        return MatchResult(False, None, top_score, "ambiguous")
    return MatchResult(True, top_user, top_score, "ok")
