import glob
import os

import cv2
import numpy as np
import pytest

from app.lean_engine import LeanEngine, _similarity, ARCFACE_DST, models_available

pytestmark = pytest.mark.skipif(not models_available(), reason="models/ not present")


def test_similarity_recovers_a_known_transform():
    th = 0.3
    m = 1.7 * np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
    src = (ARCFACE_DST - [10, 4]) @ np.linalg.inv(m).T  # points that map onto the template under m, then shifted
    est = _similarity(src.astype(np.float32), ARCFACE_DST)
    mapped = src @ est[:, :2].T + est[:, 2]
    assert np.abs(mapped - ARCFACE_DST).max() < 1e-3


def test_blank_image_has_no_faces():
    assert LeanEngine().analyse(np.full((300, 400, 3), 128, np.uint8)) == []


def _sample():
    try:
        import insightface
    except ImportError:
        pytest.skip("insightface (reference engine) not installed")
    path = os.path.join(os.path.dirname(insightface.__file__), "data", "images", "t1.jpg")
    if not os.path.exists(path):
        pytest.skip("sample image missing")
    return cv2.imread(path)


def test_same_embeddings_as_the_insightface_engine():
    from app.face_engine import InsightFaceEngine

    img = _sample()
    ref = sorted(InsightFaceEngine(modules=["detection", "recognition"]).analyse(img), key=lambda r: r.box[0])
    lean = sorted(LeanEngine().analyse(img), key=lambda r: r.box[0])
    assert len(ref) == len(lean) >= 5
    for a, b in zip(ref, lean):
        assert float(a.embedding @ b.embedding) > 0.9999
        assert abs(a.det_score - b.det_score) < 1e-3 and a.box == b.box
        assert b.yaw is None and abs(a.turn - b.turn) < 1e-3
