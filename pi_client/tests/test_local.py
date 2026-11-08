import base64
import json

import cv2
import httpx
import numpy as np
import pytest

from cashcan_pi.local import Gallery, LocalApi, _face_api_modules

FaceResult = _face_api_modules()  # makes the server's modules importable
from app.face_engine import FaceResult  # noqa: E402


def vec(seed):
    v = np.random.default_rng(seed).normal(size=512).astype(np.float32)
    return v / np.linalg.norm(v)


class Engine:
    """The image's top-left pixel says who is in front of the camera; the next pixel encodes the head turn (like the server's tests)."""

    def analyse(self, img):
        blk = img[:16, :16].reshape(-1, 3).mean(axis=0)               # blocks, not single pixels: they survive JPEG
        pid, none = int(round(blk[0])), blk[1] > 200
        if none:
            return []
        noise = np.random.default_rng().normal(scale=0.01, size=512).astype(np.float32)
        e = vec(pid) + noise
        return [FaceResult(e / np.linalg.norm(e), 0.99, (0, 0, 200, 200), 500.0, (int(round(img[16:32, :16, 0].mean())) - 128) / 200)]


def jpeg(pid, turn=0.0, noface=False):
    img = np.zeros((64, 64, 3), np.uint8)
    img[:16, :16] = (pid, 255 if noface else 0, 0)
    img[16:32, :16, 0] = int(round(turn * 200)) + 128
    return cv2.imencode(".png", img)[1].tobytes()   # png keeps the marker pixels exact; imdecode reads either


def gallery(people: dict[str, list[int]], tmp_path):
    g = Gallery(None, cache=tmp_path / "g.json")
    body = {"version": "v1", "dim": 512, "people": [
        {"user_id": u, "embeddings_b64": base64.b64encode(np.stack([vec(s) for s in seeds]).astype(np.float16).tobytes()).decode()} for u, seeds in people.items()]}
    g.parse(body)
    return g, body


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


def api(tmp_path, liveness=False, people=None):
    g, _ = gallery(people or {"alice": [1, 2], "bob": [3]}, tmp_path)
    clock = Clock()
    return LocalApi(g, Engine(), clock=clock, require_liveness=liveness), clock


def test_known_person_matches_a_stranger_and_a_bad_frame_do_not(tmp_path):
    a, _ = api(tmp_path)
    r = a.match(jpeg(1))
    assert r["matched"] and r["user_id"] == "alice" and r["score"] > 0.9 and r["session_token"]
    assert a.session(r["session_token"])["user_id"] == "alice"
    assert a.match(jpeg(99))["matched"] is False
    assert a.match(jpeg(1, noface=True))["reason"] == "bad_frame"


def test_session_expires(tmp_path):
    a, clock = api(tmp_path)
    tok = a.match(jpeg(3))["session_token"]
    assert a.session(tok)
    clock.t = 1000.0
    assert a.session(tok) is None


def test_head_turn_challenge_runs_locally_and_a_still_photo_fails(tmp_path):
    a, clock = api(tmp_path, liveness=True)
    r = a.match(jpeg(1))
    assert r["liveness_required"] and r["matched"]
    cid, d = r["challenge_id"], r["direction"]
    turn = 0.35 if d == "left" else -0.35
    assert a.liveness_frame(cid, jpeg(1, 0.0))["status"] == "pending"            # facing the camera first
    done = a.liveness_frame(cid, jpeg(1, turn))
    assert done["status"] == "passed" and done["user_id"] == "alice" and a.session(done["session_token"])
    # a still photo never turns its head: the challenge ends without a session
    r2 = a.match(jpeg(1)); cid2 = r2["challenge_id"]
    out = [a.liveness_frame(cid2, jpeg(1, 0.0))["status"] for _ in range(5)]
    assert "passed" not in out
    assert a.liveness_frame("nope", jpeg(1))["reason"] == "unknown_or_expired"


def test_same_person_can_refresh_without_a_new_challenge(tmp_path):
    a, _ = api(tmp_path, liveness=True)
    r = a.match(jpeg(1)); turn = 0.35 if r["direction"] == "left" else -0.35
    a.liveness_frame(r["challenge_id"], jpeg(1, 0.0))
    tok = a.liveness_frame(r["challenge_id"], jpeg(1, turn))["session_token"]
    again = a.match(jpeg(1), tok)
    assert again["matched"] and "liveness_required" not in again and again["session_token"]
    other = a.match(jpeg(3), tok)                                            # someone else with that token: challenged again
    assert other["liveness_required"]


def test_gallery_refresh_uses_etag_survives_network_loss_and_caches_to_disk(tmp_path):
    _, body = gallery({"alice": [1]}, tmp_path)
    calls = []

    def handler(req: httpx.Request):
        calls.append(req.headers.get("if-none-match"))
        if len(calls) == 3:
            raise httpx.ConnectError("down")
        return httpx.Response(304) if req.headers.get("if-none-match") == "v1" else httpx.Response(200, json=body)

    clk = Clock()
    g = Gallery(httpx.Client(base_url="http://x", transport=httpx.MockTransport(handler)), cache=tmp_path / "c.json", refresh=60, clock=clk)
    assert g.maybe_refresh(0.0) is True and g.owners == ["alice"]
    assert g.maybe_refresh(10.0) is False and len(calls) == 1                  # not time yet
    assert g.maybe_refresh(61.0) is False and calls[-1] == "v1"                # asked, nothing changed (304)
    assert g.maybe_refresh(130.0) is False and g.owners == ["alice"]           # network down: keeps the copy
    again = Gallery(None, cache=tmp_path / "c.json")                           # a restart with no network still has the gallery
    assert again.owners == ["alice"] and again.version == "v1"


def test_the_loop_runs_on_it_without_any_network(tmp_path):
    from cashcan_pi.indicator import ConsoleIndicator
    from cashcan_pi.loop import BinLoop

    class D:
        def has_face(self, f): return True

    a, _ = api(tmp_path)
    events = []
    loop = BinLoop(a, D(), ConsoleIndicator(out=open("/dev/null", "w")), events.append)
    frame = cv2.imdecode(np.frombuffer(jpeg(1), np.uint8), cv2.IMREAD_COLOR)
    loop.step(frame, 1.0)
    s = loop.current_session(1.1)
    assert s and s.user_id == "alice" and events[0]["event"] == "session_started"
