import json

import httpx
import numpy as np
import pytest

from cashcan_pi.api import FaceApi
from cashcan_pi.indicator import ConsoleIndicator
from cashcan_pi.loop import BinLoop

FRAME = np.zeros((480, 640, 3), np.uint8)


class FakeDetector:
    def __init__(self):
        self.face = True

    def has_face(self, frame):
        return self.face


class FakeServer:
    """Scripted /match answers + /session lookups, served through httpx's mock transport."""

    def __init__(self):
        self.match_replies, self.calls, self.down = [], 0, False

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("down")
        if request.url.path == "/match":
            self.calls += 1
            assert b"image/jpeg" in request.content  # a real JPEG upload
            return httpx.Response(200, json=self.match_replies.pop(0))
        if request.url.path.startswith("/session/"):
            return httpx.Response(200, json={"user_id": "alice", "wallet": "W"})
        return httpx.Response(404)


def matched(user="alice", token="t1"):
    return {"matched": True, "user_id": user, "score": 0.8, "session_token": token, "expires_in": 60}


def denied(reason="below_threshold"):
    return {"matched": False, "reason": reason, "score": 0.1}


@pytest.fixture
def env():
    srv, det, events = FakeServer(), FakeDetector(), []
    api = FaceApi("http://x", transport=httpx.MockTransport(srv.handler))
    loop = BinLoop(api, det, ConsoleIndicator(out=open("/dev/null", "w")), events.append)
    return srv, det, events, loop


def kinds(events):
    return [e["event"] for e in events]


def test_empty_bin_sends_nothing_except_a_slow_probe(env):
    srv, det, events, loop = env
    det.face = False
    srv.match_replies = [{"matched": False, "reason": "bad_frame", "message": "No face found."}] * 2
    for t in (0, 1, 2, 2.9):
        loop.step(FRAME, t)
    assert srv.calls == 0 and events == []
    loop.step(FRAME, 3.1)  # probe interval (3s) reached: fail-open probe
    assert srv.calls == 1 and events == []  # bad_frame on an empty bin is silent


def test_face_missed_by_local_detector_is_still_recognised_via_probe(env):
    srv, det, events, loop = env
    det.face = False  # detector blind to this face
    srv.match_replies = [matched()]
    loop.step(FRAME, 0)
    loop.step(FRAME, 3.1)
    assert kinds(events) == ["session_started"]


def test_match_opens_session_with_wallet(env):
    srv, _, events, loop = env
    srv.match_replies = [matched()]
    loop.step(FRAME, 0)
    assert events[0]["event"] == "session_started" and events[0]["wallet"] == "W"
    s = loop.current_session(1)
    assert s.user_id == "alice" and s.token == "t1"
    json.dumps(events)  # events must be JSON-serialisable (they go to stdout)


def test_uploads_are_throttled(env):
    srv, _, _, loop = env
    srv.match_replies = [denied(), denied(), denied()]
    for t in (0, 0.2, 0.4):
        loop.step(FRAME, t)
    assert srv.calls == 1  # send_interval 0.7 and denied cooldown 2.0


def test_session_expires(env):
    srv, _, events, loop = env
    srv.match_replies = [matched()]
    loop.step(FRAME, 0)
    assert loop.current_session(61) is None
    assert kinds(events) == ["session_started", "session_ended"] and events[1]["why"] == "expired"


def test_session_not_rechecked_before_interval(env):
    srv, _, _, loop = env
    srv.match_replies = [matched()]
    loop.step(FRAME, 0)
    loop.step(FRAME, 3)  # < recheck 5s
    assert srv.calls == 1


def test_different_person_replaces_session(env):
    srv, _, events, loop = env
    srv.match_replies = [matched("alice", "t1"), matched("bob", "t2")]
    loop.step(FRAME, 0)
    loop.step(FRAME, 6)
    assert kinds(events) == ["session_started", "session_ended", "session_started"]
    assert events[1]["why"] == "different_person" and loop.current_session(7).user_id == "bob"


def test_two_unrecognised_checks_end_session_but_one_does_not(env):
    srv, _, events, loop = env
    srv.match_replies = [matched(), denied(), denied()]
    loop.step(FRAME, 0)
    loop.step(FRAME, 6)
    assert loop.current_session(6) is not None  # one miss is tolerated
    loop.step(FRAME, 12)
    assert loop.current_session(12) is None and events[-1]["why"] == "unrecognised_face"


def test_bad_frame_never_ends_session(env):
    srv, _, events, loop = env
    srv.match_replies = [matched()] + [{"matched": False, "reason": "bad_frame", "message": "blurry"}] * 3
    loop.step(FRAME, 0)
    for t in (6, 12, 18):
        loop.step(FRAME, t)
    assert loop.current_session(18) is not None and kinds(events) == ["session_started"]


def test_server_down_does_not_crash_and_recovers(env):
    srv, _, events, loop = env
    srv.down = True
    loop.step(FRAME, 0)
    loop.step(FRAME, 1)  # inside backoff: no new attempt
    assert kinds(events) == ["error"]
    srv.down, srv.match_replies = False, [matched()]
    loop.step(FRAME, 4)  # backoff (3s) over
    assert kinds(events) == ["error", "session_started"]


def test_detector_falls_back_when_cascade_unavailable(monkeypatch):
    import cv2

    from cashcan_pi import detector

    monkeypatch.delattr(cv2, "CascadeClassifier", raising=False)
    warnings = []
    d = detector.make_detector(warn=warnings.append)
    assert isinstance(d, detector.AlwaysDetector) and d.has_face(FRAME) and warnings
