import math

import numpy as np

from app import config
from app.liveness import LivenessManager, turn_ratio

from .conftest import ForcedRng, enroll, png

NOSE_DEPTH = 0.8  # nose protrudes 0.8 (eye half-distance = 1): matches real data, ratio ~ 0.4*tan(yaw)


def project(yaw_deg: float, nose_depth: float) -> np.ndarray:
    """5-point face model rotated about the vertical axis, orthographic projection to the image."""
    th = math.radians(yaw_deg)
    pts = [(-1, 0, 0), (1, 0, 0), (0, -0.8, nose_depth), (-0.7, -1.6, 0), (0.7, -1.6, 0)]
    return np.array([[x * math.cos(th) + z * math.sin(th), y] for x, y, z in pts])


def test_real_head_turn_moves_the_ratio_but_a_flat_photo_does_not():
    head = [turn_ratio(project(a, NOSE_DEPTH)) for a in (0, 20, 35, 50)]
    photo = [turn_ratio(project(a, 0.0)) for a in (0, 20, 35, 50)]
    assert abs(head[0]) < 1e-9
    assert head[2] >= config.LIVENESS_TURN_MIN          # a 35 degree turn clears the bar
    assert all(abs(r) < 1e-9 for r in photo)            # photo tilted to 50 degrees: still ~0
    assert turn_ratio(project(-35, NOSE_DEPTH)) <= -config.LIVENESS_TURN_MIN  # sign flips with direction


def test_ratio_is_roll_invariant():
    kps = project(30, NOSE_DEPTH)
    a = math.radians(25)
    rot = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
    assert abs(turn_ratio(kps) - turn_ratio(kps @ rot.T)) < 1e-9


def mgr(clock, direction="left"):
    rng = ForcedRng()
    rng.direction = direction
    return LivenessManager(clock=lambda: clock["now"], rng=rng)


def test_pass_needs_center_then_turn_in_the_asked_direction(clock):
    m = mgr(clock, "left")
    cid, d, _ = m.create("alice")
    assert d == "left"
    assert m.submit(cid, 0.0, 0.9).status == "pending"
    assert m.submit(cid, 0.30, 0.9).status == "passed"
    assert m.submit(cid, 0.30, 0.9).reason == "unknown_or_expired"  # single use


def test_wrong_direction_does_not_pass(clock):
    m = mgr(clock, "left")
    cid, *_ = m.create("alice")
    m.submit(cid, 0.0, 0.9)
    assert m.submit(cid, -0.40, 0.9).status == "pending"


def test_must_start_facing_the_camera(clock):
    m = mgr(clock, "right")
    cid, *_ = m.create("alice")
    assert m.submit(cid, -0.40, 0.9).status == "pending"  # already turned: no credit
    assert m.submit(cid, -0.40, 0.9).status == "pending"


def test_static_photo_never_passes_and_expires(clock):
    m = mgr(clock)
    cid, *_ = m.create("alice")
    for t in range(0, 9):
        clock["now"] = t
        assert m.submit(cid, 0.02, 0.95).status == "pending"
    clock["now"] = config.LIVENESS_TTL_SECONDS + 1
    r = m.submit(cid, 0.02, 0.95)
    assert r.status == "failed" and r.reason == "expired"


def test_different_person_fails_after_strikes(clock):
    m = mgr(clock)
    cid, *_ = m.create("alice")
    out = [m.submit(cid, 0.0, 0.05).status for _ in range(config.LIVENESS_MAX_STRIKES)]
    assert out[:-1] == ["pending"] * (config.LIVENESS_MAX_STRIKES - 1) and out[-1] == "failed"


def test_open_challenges_are_capped(clock, monkeypatch):
    monkeypatch.setattr(config, "LIVENESS_MAX_OPEN", 3)
    m = mgr(clock)
    ids = []
    for i in range(5):
        clock["now"] = i
        ids.append(m.create("alice")[0])
    assert m.user_for(ids[0]) is None and m.user_for(ids[-1]) == "alice"


# ---- through the HTTP API
def match(c, pid, **kw):
    return c.post("/match", files={"frame": ("m.png", png(pid, **kw), "image/png")}).json()


def send(c, cid, pid, turn=0.0, **kw):
    return c.post(f"/liveness/{cid}/frame", files={"frame": ("f.png", png(pid, turn=turn, **kw), "image/png")}).json()


def turn_for(direction, amount=0.35):
    return amount if direction == "left" else -amount


def test_match_returns_challenge_not_session(live_client):
    enroll(live_client, "alice", 1)
    r = match(live_client, 1)
    assert r["matched"] and r["liveness_required"] and r["direction"] in ("left", "right")
    assert "session_token" not in r


def test_full_flow_issues_session_only_after_turn(live_client):
    enroll(live_client, "alice", 1)
    r = match(live_client, 1)
    cid, d = r["challenge_id"], r["direction"]
    assert send(live_client, cid, 1, 0.0)["status"] == "pending"
    done = send(live_client, cid, 1, turn_for(d))
    assert done["status"] == "passed" and done["user_id"] == "alice"
    assert live_client.get(f"/session/{done['session_token']}").json()["user_id"] == "alice"


def test_photo_attack_gets_no_session(live_client, clock):
    enroll(live_client, "alice", 1)
    r = match(live_client, 1)
    for _ in range(5):
        assert send(live_client, r["challenge_id"], 1, 0.0)["status"] == "pending"
    clock["now"] = 11
    out = send(live_client, r["challenge_id"], 1, 0.0)
    assert out["status"] == "failed" and "session_token" not in out


def test_someone_else_answering_the_challenge_fails(live_client):
    enroll(live_client, "alice", 1)
    r = match(live_client, 1)
    outs = [send(live_client, r["challenge_id"], 2, 0.0)["status"] for _ in range(3)]  # person 2's face
    assert outs[-1] == "failed"


def test_bad_frame_is_not_a_failure(live_client):
    enroll(live_client, "alice", 1)
    r = match(live_client, 1)
    out = send(live_client, r["challenge_id"], 1, 0.0, noface=True)
    assert out["status"] == "pending" and out["hint"]


def test_unknown_challenge(live_client):
    assert send(live_client, "nope", 1)["reason"] == "unknown_or_expired"


def test_same_person_can_refresh_without_new_challenge_until_window_ends(live_client, clock):
    enroll(live_client, "alice", 1)
    r = match(live_client, 1)
    send(live_client, r["challenge_id"], 1, 0.0)
    tok = send(live_client, r["challenge_id"], 1, turn_for(r["direction"]))["session_token"]

    def refresh(token):
        return live_client.post("/match", files={"frame": ("m.png", png(1), "image/png")}, data={"session_token": token}).json()

    for t in (30, 60, 90, 119):  # a real client refreshes continuously; each token lives 60s
        clock["now"] = t
        tok = refresh(tok)
        assert tok["matched"] and "liveness_required" not in tok  # still inside 120s of the ORIGINAL proof
        tok = tok["session_token"]
    clock["now"] = 125  # window over: refreshes never extended it, so prove liveness again
    assert refresh(tok).get("liveness_required") is True


def test_refresh_for_a_different_person_needs_a_challenge(live_client):
    enroll(live_client, "alice", 1)
    enroll(live_client, "bob", 2)
    r = match(live_client, 1)
    send(live_client, r["challenge_id"], 1, 0.0)
    tok = send(live_client, r["challenge_id"], 1, turn_for(r["direction"]))["session_token"]
    out = live_client.post("/match", files={"frame": ("m.png", png(2), "image/png")}, data={"session_token": tok}).json()
    assert out["user_id"] == "bob" and out["liveness_required"] is True
