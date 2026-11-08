from cashcan_pi.canwatch import CanWatcher


class Lid:
    def __init__(self):
        self.calls = []

    def set_open(self, b, o):
        self.calls.append((b, o))


def feed(w, seq, start=0.0, dt=0.2):
    t = start
    for p in seq:
        w.update({"cans": p, "waste": 1 - p}, t)
        t += dt
    return t


def test_no_can_never_opens():
    lid = Lid()
    feed(CanWatcher(lid), [0.1] * 20)
    assert lid.calls == []


def test_a_can_seen_on_a_few_looks_opens_the_lid():
    lid = Lid()
    feed(CanWatcher(lid), [0.9] * 3)
    assert lid.calls == [("cans", True)]


def test_one_odd_frame_does_nothing():
    lid = Lid()
    feed(CanWatcher(lid), [0.9, 0.1, 0.9, 0.1, 0.9])
    assert lid.calls == []


def test_stays_open_while_the_can_is_there_and_closes_after_it_is_gone():
    lid = Lid()
    w = CanWatcher(lid, hold=3.0)
    t = feed(w, [0.9] * 10)
    assert lid.calls == [("cans", True)]
    t = feed(w, [0.0] * 5, start=t)               # 1 s without a can: still open
    assert lid.calls == [("cans", True)]
    feed(w, [0.0] * 20, start=t)                  # long enough: shut, once
    assert lid.calls == [("cans", True), ("cans", False)]
