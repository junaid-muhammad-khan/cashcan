import numpy as np

from app.smoothing import EmbeddingSmoother
from tools.face_demo import GUIDED_STEPS, GUIDED_TOTAL, GuidedPlan, apply_smoothing, FaceReport


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def unit(seed):
    v = np.random.default_rng(seed).normal(size=512).astype(np.float32)
    return v / np.linalg.norm(v)


def near(v, s, seed):
    y = v + s * np.random.default_rng(seed).normal(size=512).astype(np.float32)
    return y / np.linalg.norm(y)


# ---- guided enrollment plan
def test_plan_waits_for_lead_collects_then_advances_and_finishes():
    c = Clock()
    p = GuidedPlan(lead=3.0, timeout=10.0, clock=c)
    assert not p.collecting() and p.countdown() == 3 and "Step 1/" in p.status()
    c.t = 3.0
    assert p.collecting()
    first_need = GUIDED_STEPS[0][1]
    for _ in range(first_need):
        p.got_frame()
    assert p.index == 1 and not p.collecting()          # advanced; the next step starts with its own lead time
    for step in range(1, len(GUIDED_STEPS)):
        c.t += 3.0
        assert p.collecting()
        for _ in range(GUIDED_STEPS[step][1]):
            p.got_frame()
    assert p.done and p.status() == "done" and GUIDED_TOTAL == sum(n for _, n in GUIDED_STEPS)


def test_plan_gives_up_on_a_step_that_never_gets_a_usable_frame():
    c = Clock()
    p = GuidedPlan(lead=2.0, timeout=5.0, clock=c)
    c.t = 6.9
    assert p.collecting() and p.index == 0              # still within lead + timeout
    c.t = 7.1
    p.collecting()
    assert p.index == 1                                 # skipped, so one impossible step cannot block the rest


# ---- smoothing
def test_average_is_steadier_than_a_single_noisy_frame():
    me = unit(1)
    frames = [near(me, 0.012, 100 + i) for i in range(5)]   # seeds differ from the base face's seed
    s = EmbeddingSmoother(size=5, clock=Clock())
    out = [s.add(f) for f in frames]
    single = [float(f @ me) for f in frames]
    assert out[-1][1] == 5
    assert min(single) < 0.97                               # the single frames really are noisy
    assert float(out[-1][0] @ me) > np.mean(single) + 0.01  # and the average of 5 is clearly closer than a typical single frame


def test_a_different_person_stepping_in_clears_the_window():
    s = EmbeddingSmoother(size=5, clock=Clock())
    for i in range(3):
        s.add(near(unit(1), 0.01, 100 + i))
    emb, n = s.add(unit(99))                             # unrelated face
    assert n == 1 and float(emb @ unit(99)) > 0.99      # judged on its own, not blended with the first person


def test_window_clears_when_the_face_was_gone_for_a_moment():
    c = Clock()
    s = EmbeddingSmoother(size=5, gap_seconds=1.0, clock=c)
    s.add(unit(1)); c.t = 0.5
    assert s.add(unit(1))[1] == 2
    c.t = 3.0
    assert s.add(unit(1))[1] == 1


def test_apply_smoothing_only_touches_the_main_face_and_reports_the_average(tmp_path):
    from app.store import FaceStore

    store = FaceStore(str(tmp_path / "s.db"))
    me = unit(1)
    store.add_user("me", "W", [me, near(me, 0.01, 101), near(me, 0.01, 102)])
    mk = lambda emb, box: FaceReport(box, True, "", False, None, 0.1, "below_threshold", embedding=emb)
    sm = EmbeddingSmoother(size=5, clock=Clock())
    big, small = (0, 0, 200, 200), (300, 0, 340, 40)
    first = apply_smoothing([mk(near(me, 0.012, 105), big), mk(unit(50), small)], sm, store, 0.45, 0.05)
    second = apply_smoothing([mk(near(me, 0.012, 106), big), mk(unit(50), small)], sm, store, 0.45, 0.05)
    assert first[0].n_avg == 1 and second[0].n_avg == 2 and second[0].matched and second[0].name == "me"
    assert "(avg of 2)" in second[0].label and second[1].n_avg == 1 and not second[1].matched   # the small face is left alone
