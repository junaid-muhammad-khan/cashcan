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
    """Image pixel [0,0,0] = person id, [0,0,1] = 255 means 'no face', [0,0,2] = quality flag."""

    def analyse(self, img):
        pid, noface, bad = int(img[0, 0, 0]), img[0, 0, 1] == 255, img[0, 0, 2] == 255
        if noface:
            return []
        noise = np.random.default_rng().normal(scale=0.01, size=512).astype(np.float32)
        v = person_vec(pid) + noise
        v /= np.linalg.norm(v)
        return [FaceResult(v, 0.3 if bad else 0.99, (0, 0, 200, 200), 500.0)]


def png(pid: int, noface=False, bad=False) -> bytes:
    img = np.zeros((32, 32, 3), np.uint8)
    img[0, 0] = (pid, 255 if noface else 0, 255 if bad else 0)
    return cv2.imencode(".png", img)[1].tobytes()


@pytest.fixture
def clock():
    t = {"now": 0.0}
    return t


@pytest.fixture
def client(tmp_path, clock):
    app = create_app(FakeEngine(), FaceStore(str(tmp_path / "t.db")),
                     SessionManager(ttl=60, clock=lambda: clock["now"]))
    return TestClient(app)


def enroll(client, user, pid, n=3, consent=True, **kw):
    files = [("frames", (f"f{i}.png", png(pid, **kw), "image/png")) for i in range(n)]
    return client.post("/enroll", data={"user_id": user, "wallet": WALLET, "consent": str(consent).lower()},
                       files=files)
