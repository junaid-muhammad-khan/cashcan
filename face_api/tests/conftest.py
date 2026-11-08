import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.face_engine import FaceResult
from app.main import create_app
from app.sessions import SessionManager
from app.store import FaceStore


WALLET = "9xQeWvG816bUx9EPjHmaT23yvVM2ZWbrrpZb9PusVFin"


def person_vec(pid: int) -> np.ndarray:
    v = np.random.default_rng(pid).normal(size=512).astype(np.float32)
    return v / np.linalg.norm(v)


class FakeEngine:
    """Image pixel [0,0,0] = person id, [0,0,1] = 255 means 'no face', [0,0,2] = quality flag,
    [1,0,0] = head-turn ratio encoded as round(turn*200)+128."""

    def analyse(self, img):
        pid, noface, bad = int(img[0, 0, 0]), img[0, 0, 1] == 255, img[0, 0, 2] == 255
        if noface:
            return []
        noise = np.random.default_rng().normal(scale=0.01, size=512).astype(np.float32)
        v = person_vec(pid) + noise
        v /= np.linalg.norm(v)
        turn = (int(img[1, 0, 0]) - 128) / 200
        return [FaceResult(v, 0.3 if bad else 0.99, (0, 0, 200, 200), 500.0, turn)]


def png(pid: int, noface=False, bad=False, turn=0.0) -> bytes:
    img = np.zeros((32, 32, 3), np.uint8)
    img[0, 0] = (pid, 255 if noface else 0, 255 if bad else 0)
    img[1, 0, 0] = int(round(turn * 200)) + 128
    return cv2.imencode(".png", img)[1].tobytes()


@pytest.fixture
def clock():
    t = {"now": 0.0}
    return t


class ForcedRng:
    """Makes the random challenge direction predictable in tests."""
    direction = "left"

    def choice(self, seq):
        return self.direction


def _make(tmp_path, clock, liveness_on, monkeypatch):
    from app import config
    from app.liveness import LivenessManager

    monkeypatch.setattr(config, "REQUIRE_LIVENESS", liveness_on)
    now = lambda: clock["now"]
    app = create_app(FakeEngine(), FaceStore(str(tmp_path / "t.db")), SessionManager(ttl=60, clock=now),
                     LivenessManager(clock=now, rng=ForcedRng()))
    return TestClient(app)


@pytest.fixture
def client(tmp_path, clock, monkeypatch):
    """Liveness OFF: the original match -> session behaviour."""
    return _make(tmp_path, clock, False, monkeypatch)


@pytest.fixture
def live_client(tmp_path, clock, monkeypatch):
    """Liveness ON: match -> challenge -> frames -> session."""
    return _make(tmp_path, clock, True, monkeypatch)


def enroll(client, user, pid, n=3, consent=True, **kw):
    files = [("frames", (f"f{i}.png", png(pid, **kw), "image/png")) for i in range(n)]
    return client.post("/enroll", data={"user_id": user, "wallet": WALLET, "consent": str(consent).lower()},
                       files=files)
