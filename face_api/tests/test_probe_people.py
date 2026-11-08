import numpy as np

from tools.probe_people import render, score_frame, summarise


def unit(seed):
    v = np.random.default_rng(seed).normal(size=512).astype(np.float32)
    return v / np.linalg.norm(v)


def test_outcomes():
    owners, gal = ["a", "a", "b"], np.stack([unit(1), unit(2), unit(3)])
    near = unit(1) + 0.1 * unit(9); near /= np.linalg.norm(near)
    assert score_frame(near, owners, gal, "a")["outcome"] == "correct"
    assert score_frame(near, owners, gal, "b")["outcome"] == "wrong_name"      # the camera shows a, but b was expected
    assert score_frame(unit(50), owners, gal, "a")["outcome"] == "unknown"


def test_summary_and_report():
    rows = [{"outcome": "correct", "right": .7, "wrong": .1}, {"outcome": "correct", "right": .6, "wrong": .2},
            {"outcome": "unknown", "right": .3, "wrong": .1}, {"outcome": "skipped", "right": 0, "wrong": 0}]
    s = summarise(rows)
    assert (s["correct"], s["unknown"], s["skipped"], s["frames"]) == (2, 1, 1, 4) and s["right_min"] == .3 and s["wrong_max"] == .2
    text = render({"junaid": rows}, .45, .05)
    assert "2 (50%)" in text and "2/3 (67%)" in text and "**All**" in text
