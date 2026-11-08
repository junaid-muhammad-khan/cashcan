import httpx
import numpy as np
import pytest

from cashcan_pi.classifier import OnnxClassifier, decide, preprocess
from cashcan_pi.controller import BinController, Outbox
from cashcan_pi.itemgate import ItemGate
from cashcan_pi.lid import CommandLid, LidController, SimulatedLid
from cashcan_pi.loop import Session

EMPTY = np.full((480, 640, 3), 90, np.uint8)


def with_item():
    f = EMPTY.copy()
    f[250:430, 200:440] = (30, 60, 200)   # a solid object inside the default ROI
    return f


class Gate(ItemGate):
    pass


def run_gate(frames_at):
    g, fired = ItemGate(warmup=0.5, settle=0.5, clear_for=0.5), []
    for t, f in frames_at:
        if g.step(f, t):
            fired.append(t)
    return g, fired


def test_gate_fires_once_when_an_item_settles_then_waits_for_it_to_leave():
    seq = [(t / 10, EMPTY) for t in range(0, 12)] + [(1.2 + t / 10, with_item()) for t in range(0, 30)] \
        + [(4.2 + t / 10, EMPTY) for t in range(0, 20)] + [(6.2 + t / 10, with_item()) for t in range(0, 20)]
    g, fired = run_gate(seq)
    assert len(fired) == 2 and 1.6 < fired[0] < 2.4 and fired[1] > 6.2   # one per item, not one per frame


def test_gate_ignores_motion_and_empty_view():
    rng = np.random.default_rng(0)
    seq = [(t / 10, EMPTY) for t in range(0, 12)]
    seq += [(1.2 + t / 10, np.clip(with_item().astype(int) + rng.integers(-60, 60, EMPTY.shape), 0, 255).astype(np.uint8)) for t in range(0, 20)]  # flickering
    assert run_gate(seq)[1] == []


def test_decide_averages_and_falls_back_to_waste_when_unsure():
    sure = [{"cans": 0.9, "organics": 0.05, "waste": 0.05}] * 3
    assert decide(sure, 0.6) == ("cans", pytest.approx(0.9), "ok")
    unsure = [{"cans": 0.4, "organics": 0.35, "waste": 0.25}] * 3
    assert decide(unsure, 0.6)[0] == "waste" and decide(unsure, 0.6)[2] == "low_confidence"


def test_real_model_loads_and_returns_probabilities_for_all_bins():
    c = OnnxClassifier()
    p = c.probs(with_item())
    assert set(p) == {"cans", "organics", "waste"} and abs(sum(p.values()) - 1) < 1e-4
    assert preprocess(with_item()).shape == (1, 3, 224, 224)


# ---- controller -------------------------------------------------------------------------------
class FakeLoop:
    def __init__(self, session=None):
        self.session, self.stepped = session, 0

    def step(self, frame, now):
        self.stepped += 1

    def current_session(self, now):
        return self.session


class FireOnce:
    def __init__(self):
        self.fired = False
        self.roi = (0, 0, 1, 1)

    def crop(self, f):
        return f

    def step(self, f, now):
        if not self.fired:
            self.fired = True
            return True
        return False


class FakeClassifier:
    def __init__(self, p):
        self.p = p

    def probs(self, f):
        return self.p


class FakeApi:
    def __init__(self):
        self.sent, self.fail = [], None

    def interaction(self, payload):
        if self.fail == "net":
            raise httpx.ConnectError("down")
        if self.fail == 500:
            raise httpx.HTTPStatusError("x", request=httpx.Request("POST", "http://x"), response=httpx.Response(500))
        if self.fail == 401:
            raise httpx.HTTPStatusError("x", request=httpx.Request("POST", "http://x"), response=httpx.Response(401))
        self.sent.append(payload)
        paying = payload["item_class"] == "cans" and "session_token" in payload
        return {"duplicate": False, "reward_cents": 5 if paying else 0, "payout_status": "paid" if paying else "none",
                "reason": None if paying else "not_recognised"}


def make(session, probs, api=None):
    api, events, drv = api or FakeApi(), [], SimulatedLid(out=open("/dev/null", "w"))
    ids = iter(f"id-{i}" for i in range(100))
    c = BinController(FakeLoop(session), FireOnce(), FakeClassifier(probs), LidController(drv, hold=5), Outbox(api, on_event=events.append),
                      events.append, votes=1, new_id=lambda: next(ids))
    return c, api, events, drv


CANS = {"cans": 0.92, "organics": 0.05, "waste": 0.03}
SESSION = Session("user-1", None, "tok123", 999.0)


def test_verified_person_throws_a_can_right_lid_opens_and_a_reward_is_due():
    c, api, events, drv = make(SESSION, CANS)
    c.step(EMPTY, 1.0)
    assert drv.log == [("cans", True)]
    assert api.sent == [{"interaction_id": "id-0", "item_class": "cans", "confidence": 0.92, "session_token": "tok123", "user_id": "user-1"}]   # no amount
    assert any(e["event"] == "item" and e["user_id"] == "user-1" for e in events)
    rec = next(e for e in events if e["event"] == "interaction_recorded")
    assert rec["reward_cents"] == 5 and rec["payout_status"] == "paid" and c.last_item["payout_status"] == "paid"


def test_nobody_identified_lid_still_opens_but_no_session_and_no_reward():
    c, api, events, drv = make(None, CANS)
    c.step(EMPTY, 1.0)
    assert drv.log == [("cans", True)]
    assert "reward_lamports" not in api.sent[0] and "session_token" not in api.sent[0]
    assert c.last_item["payout_status"] == "none" and c.last_item["reward_cents"] == 0


def test_waste_never_pays_and_unsure_items_go_to_waste():
    c, api, _, drv = make(SESSION, {"cans": 0.4, "organics": 0.35, "waste": 0.25})
    c.step(EMPTY, 1.0)
    assert drv.log == [("waste", True)] and api.sent[0]["item_class"] == "waste" and "reward_lamports" not in api.sent[0]


def test_lid_closes_after_the_hold_time_and_never_two_open():
    c, _, _, drv = make(SESSION, CANS)
    c.step(EMPTY, 1.0)
    c.lid.open("organics", 2.0)
    assert drv.log == [("cans", True), ("cans", False), ("organics", True)]
    c.step(EMPTY, 8.0)
    assert drv.log[-1] == ("organics", False) and c.lid.open_bin is None


def test_network_down_queues_the_record_and_retries_with_the_same_id():
    api = FakeApi(); api.fail = "net"
    c, _, events, _ = make(SESSION, CANS, api)
    c.step(EMPTY, 1.0)
    assert api.sent == [] and len(c.outbox.items) == 1 and any(e["event"] == "interaction_queued" for e in events)
    api.fail = None
    c.step(EMPTY, 2.0)      # too early: backoff
    assert api.sent == []
    c.step(EMPTY, 7.0)
    assert [p["interaction_id"] for p in api.sent] == ["id-0"] and c.outbox.items == []


def test_outbox_drops_after_ttl_and_on_a_permanent_refusal():
    api = FakeApi(); api.fail = "net"
    c, _, events, _ = make(SESSION, CANS, api)
    c.step(EMPTY, 1.0)
    c.step(EMPTY, 2000.0)   # long past the 600 s TTL
    assert c.outbox.items == [] and any(e.get("why") == "expired" for e in events)
    api2 = FakeApi(); api2.fail = 401
    c2, _, ev2, _ = make(SESSION, CANS, api2)
    c2.step(EMPTY, 1.0)
    assert c2.outbox.items == [] and any(e["event"] == "interaction_rejected" for e in ev2)   # bad bin key: not retried forever


def test_command_lid_runs_the_configured_command_per_bin():
    ran = []
    d = CommandLid({"cans": {"open": "servo --pin 5 --angle 90", "close": "servo --pin 5 --angle 0"}}, runner=ran.append)
    d.set_open("cans", True); d.set_open("cans", False); d.set_open("organics", True)   # organics has no command: ignored
    assert ran == [["servo", "--pin", "5", "--angle", "90"], ["servo", "--pin", "5", "--angle", "0"]]


def test_preview_overlay_draws_every_state_without_error():
    from cashcan_pi.preview import draw
    frame = np.full((480, 640, 3), 90, np.uint8)
    roi = (0.15, 0.4, 0.85, 1.0)
    idle = {"user_id": None, "gate": "empty", "collecting_looks": False, "open_lid": None, "last_item": None}
    item = {"bin": "cans", "confidence": 0.93, "reason": "ok", "user_id": "abcdef123456", "payout_status": "paid", "reward_cents": 5}
    for st, ind in ((idle, "idle"), (idle, "challenge"), ({**idle, "collecting_looks": True}, "scanning"),
                    ({**idle, "user_id": "abcdef123456", "gate": "present", "open_lid": "cans", "last_item": item}, "matched"),
                    ({**idle, "last_item": {**item, "bin": "waste", "reason": "low_confidence", "user_id": None, "payout_status": "none", "reward_cents": 0}}, "denied"),
                    ({**idle, "last_item": {**item, "payout_status": "held"}}, "matched"),
                    ({**idle, "last_item": {**item, "payout_status": None, "reward_cents": None}}, "matched")):
        out = draw(frame, st, ind, "hint text", roi)
        assert out.shape == frame.shape and (out != frame).any()
    assert (frame == 90).all()   # the input frame is not modified


def test_controller_status_snapshot():
    c, _, _, _ = make(SESSION, CANS)
    c.step(EMPTY, 1.0)
    st = c.status(2.0)
    assert st["user_id"] == "user-1" and st["open_lid"] == "cans" and st["last_item"]["bin"] == "cans" and st["collecting_looks"] is False
    assert c.status(100.0)["last_item"] is None   # stale decisions fade from the display


def test_background_identity_never_blocks_the_camera_loop():
    import threading, time
    from cashcan_pi.threaded import BackgroundIdentity

    class SlowLoop:
        face_seen, _session = True, None
        last_reply = {"matched": False, "reason": "below_threshold", "score": 0.3}

        def __init__(self):
            self.frames, self.emit = [], lambda e: None

        def step(self, frame, now):
            time.sleep(0.5)               # a slow server answer
            self.frames.append(frame)

    slow = SlowLoop()
    bg = BackgroundIdentity(slow)
    t = time.monotonic()
    for i in range(50):                   # the camera loop keeps going while the server is slow
        bg.step(i, time.monotonic())
    assert time.monotonic() - t < 0.2
    time.sleep(1.3)
    bg.stop()
    assert 1 <= len(slow.frames) <= 3 and slow.frames[-1] == 49      # stale frames were dropped; the newest one was used
    assert bg.info()["last_reply"]["reason"] == "below_threshold" and bg.current_session(0.0) is None


def test_loop_remembers_face_seen_and_last_reply():
    from cashcan_pi.indicator import ConsoleIndicator
    from cashcan_pi.loop import BinLoop

    class D:
        def has_face(self, f): return True

    class A:
        def match(self, jpeg, token=None): return {"matched": False, "reason": "below_threshold", "score": 0.31}

    lp = BinLoop(A(), D(), ConsoleIndicator(out=open("/dev/null", "w")))
    lp.step(EMPTY, 1.0)
    assert lp.face_seen is True and lp.last_reply["reason"] == "below_threshold"


def test_item_photos_are_saved_with_the_decision_in_the_name(tmp_path):
    c, _, _, _ = make(SESSION, CANS)
    c.save_dir = str(tmp_path / "photos")
    c.step(with_item(), 1.0)
    files = list((tmp_path / "photos").glob("*.jpg"))
    assert len(files) == 1 and "_cans_92_" in files[0].name and "unsure" not in files[0].name and files[0].stat().st_size > 500
    c2, _, _, _ = make(None, {"cans": 0.4, "organics": 0.35, "waste": 0.25})
    c2.save_dir = str(tmp_path / "p2")
    c2.step(with_item(), 1.0)
    assert "_waste_" in next((tmp_path / "p2").glob("*.jpg")).name and "_unsure_" in next((tmp_path / "p2").glob("*.jpg")).name


def test_item_crop_is_tight_square_around_the_item_and_a_person_filling_the_box_is_not_an_item():
    g = ItemGate(warmup=0.5, settle=0.5)
    for t in range(0, 12):
        g.step(EMPTY, t / 10)
    small = EMPTY.copy(); small[300:360, 300:360] = (20, 200, 230)        # a small item inside the box
    fired = [g.step(small, 1.2 + t / 10) for t in range(0, 15)]
    assert any(fired)
    crop = g.item_crop(small)
    assert crop.shape[0] == crop.shape[1] and crop.shape[0] < g.crop(small).shape[0] * 0.5   # square, much smaller than the whole box
    cy, cx = crop.shape[0] // 2, crop.shape[1] // 2
    assert tuple(crop[cy, cx]) == (20, 200, 230)                                            # and the item is in the middle of it
    person = ItemGate(warmup=0.5, settle=0.5)
    for t in range(0, 12):
        person.step(EMPTY, t / 10)
    body = np.full((480, 640, 3), (40, 40, 160), np.uint8)               # a torso: the whole box changes
    assert not any(person.step(body, 1.2 + t / 10) for t in range(0, 20))


def test_teaching_makes_the_bin_recognise_what_it_was_shown(tmp_path):
    import cv2
    from cashcan_pi.classifier import TeachableClassifier

    rng = np.random.default_rng(1)
    can = np.clip(rng.normal(120, 60, (200, 200, 3)), 0, 255).astype(np.uint8); can[40:160, 70:130] = (20, 20, 220)     # a red tall thing
    other = np.clip(rng.normal(120, 60, (200, 200, 3)), 0, 255).astype(np.uint8); other[60:140, 40:160] = (230, 230, 30)  # something else
    c = TeachableClassifier(store=tmp_path / "t.npz", photos=tmp_path / "ph")
    before = c.probs(can)
    assert c.teach("cans", can) == 1 and c.teach("waste", other) == 1
    after = c.probs(can)
    assert max(after, key=after.get) == "cans" and after["cans"] > before["cans"]            # what was shown is now recognised
    assert max(c.probs(other), key=c.probs(other).get) == "waste"
    assert len(list((tmp_path / "ph" / "cans").glob("*.jpg"))) == 1                           # the taught photo is kept for retraining
    again = TeachableClassifier(store=tmp_path / "t.npz", photos=tmp_path / "ph")             # and it is remembered after a restart
    assert again.labels == ["cans", "waste"] and max(again.probs(can), key=again.probs(can).get) == "cans"
    assert again.forget_last() == "waste" and again.labels == ["cans"]
    with pytest.raises(ValueError):
        c.teach("metal", can)


class StateGate:
    """A gate whose state the test controls: fires once, then stays 'present' until set to 'empty'."""
    roi = (0, 0, 1, 1)

    def __init__(self):
        self.state, self._fire = "empty", True

    def crop(self, f):
        return f

    def step(self, f, now):
        if self._fire and self.state == "empty":
            self._fire, self.state = False, "present"
            return True
        return False


class ScriptedClassifier:
    """Answers whatever the test sets; supports teaching like the real one."""

    def __init__(self, p):
        self.p, self.taught = p, []
        self.labels = []

    def probs(self, f):
        return self.p

    def teach(self, label, crop):
        self.labels.append(label)
        self.p = {"cans": 0.95, "organics": 0.02, "waste": 0.03} if label == "cans" else self.p
        return len(self.labels)

    def forget_last(self):
        return self.labels.pop() if self.labels else None


def make_live(probs):
    api, events, drv, gate = FakeApi(), [], SimulatedLid(out=open("/dev/null", "w")), StateGate()
    ids = iter(f"id-{i}" for i in range(100))
    clf = ScriptedClassifier(probs)
    c = BinController(FakeLoop(SESSION), gate, clf, LidController(drv, hold=30), Outbox(api, on_event=events.append), events.append,
                      votes=1, new_id=lambda: next(ids), reeval_interval=1.0)
    return c, api, events, drv, gate, clf


def test_the_item_is_judged_again_every_second_and_a_confident_change_moves_the_lid():
    c, api, events, drv, gate, clf = make_live({"cans": 0.2, "organics": 0.1, "waste": 0.7})
    c.step(EMPTY, 1.0)
    assert drv.log == [("waste", True)] and c.last_item["bin"] == "waste"
    c.step(EMPTY, 1.5)                                          # too soon: not looked at again
    assert clf.p["waste"] == 0.7 and len(api.sent) == 1
    clf.p = {"cans": 0.9, "organics": 0.05, "waste": 0.05}      # the person turns the can so its shape shows
    c.step(EMPTY, 2.2)
    assert c.last_item["bin"] == "waste"                        # one look is not enough: the last three looks are averaged
    c.step(EMPTY, 3.4)
    assert c.last_item["bin"] == "cans" and drv.log[-2:] == [("waste", False), ("cans", True)]
    assert any(e["event"] == "item_revised" and e["from"] == "waste" and e["bin"] == "cans" for e in events)
    assert [p["item_class"] for p in api.sent] == ["waste", "cans"]    # the corrected item is recorded too (new id)
    clf.p = {"cans": 0.4, "organics": 0.3, "waste": 0.3}        # a single unsure look does not flip a confident decision
    c.step(EMPTY, 4.6)
    assert drv.log[-1] == ("cans", True) and len(api.sent) == 2


def test_nothing_is_recorded_twice_and_the_decision_is_forgotten_when_the_item_leaves():
    c, api, events, drv, gate, clf = make_live({"cans": 0.9, "organics": 0.05, "waste": 0.05})
    c.step(EMPTY, 1.0)
    for t in (2.2, 3.4, 4.6):
        c.step(EMPTY, t)
    assert len(api.sent) == 1                                   # same answer each second: still one record
    gate.state = "empty"; gate._fire = True
    c.step(EMPTY, 6.0)                                          # item left, a new one arrives
    assert len(api.sent) == 2


def test_teaching_in_the_window_fixes_the_decision_straight_away():
    c, api, events, drv, gate, clf = make_live({"cans": 0.05, "organics": 0.05, "waste": 0.9})     # a soda can wrongly called waste
    c.step(EMPTY, 1.0)
    assert c.last_item["bin"] == "waste"
    assert c.teach("cans", 1.2) == {"label": "cans", "examples": 1}
    assert c.last_item["bin"] == "cans" and drv.log[-1] == ("cans", True)
    assert api.sent[-1]["item_class"] == "cans" and c.status(1.3)["can_teach"] and c.status(1.3)["taught"] == 1
    assert c.forget_last_teaching() == "cans"
