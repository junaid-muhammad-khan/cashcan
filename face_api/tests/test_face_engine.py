import cv2
import numpy as np

from app.face_engine import face_sharpness


def textured_face(size: int) -> np.ndarray:
    """A synthetic 'face': smooth shapes plus fine texture and edges, rendered at a given size."""
    rng = np.random.default_rng(0)
    base = cv2.resize(rng.integers(0, 255, (60, 60, 3), dtype=np.uint8), (800, 800), interpolation=cv2.INTER_CUBIC)
    cv2.circle(base, (400, 400), 300, (200, 180, 160), 6)
    cv2.line(base, (250, 300), (550, 300), (20, 20, 20), 8)
    return cv2.resize(base, (size, size), interpolation=cv2.INTER_AREA if size < 800 else cv2.INTER_CUBIC)


def raw_laplacian(img):
    return float(cv2.Laplacian(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var())


def test_sharpness_does_not_depend_on_how_big_the_face_is():
    small, big = textured_face(120), textured_face(560)
    box = lambda im: (0, 0, im.shape[1], im.shape[0])
    ratio_raw = raw_laplacian(small) / raw_laplacian(big)
    ratio_norm = face_sharpness(small, box(small)) / face_sharpness(big, box(big))
    assert ratio_raw > 5                    # the old measure swings by an order of magnitude with size alone
    assert 0.5 < ratio_norm < 2.0           # the normalised one is comparable at any distance


def test_sharpness_still_drops_with_real_blur():
    img = textured_face(300)
    box = (0, 0, 300, 300)
    sharp = face_sharpness(img, box)
    soft = face_sharpness(cv2.GaussianBlur(img, (0, 0), 3), box)
    assert soft < 0.3 * sharp


def test_empty_or_degenerate_box_is_safe():
    img = textured_face(100)
    assert face_sharpness(img, (500, 500, 600, 600)) == 0.0
    assert face_sharpness(img, (-20, -20, 50, 50)) >= 0.0


def test_sharpness_does_not_confuse_dim_light_with_blur():
    img = textured_face(300)
    box = (0, 0, 300, 300)
    normal = face_sharpness(img, box)
    dim = face_sharpness((img * 0.25).astype(np.uint8), box)
    side = np.clip(img.astype(np.float32) * np.linspace(1.0, 0.15, 300, dtype=np.float32)[None, :, None], 0, 255).astype(np.uint8)
    assert 0.6 < dim / normal < 1.6             # a quarter of the light is not a quarter of the sharpness
    # a lighting GRADIENT (window on one side) cannot be fully normalised away, but it must not look like blur either
    assert face_sharpness(side, box) / normal > 0.25
    assert face_sharpness(cv2.GaussianBlur(img, (0, 0), 4), box) < 0.25 * normal   # real blur still reads as blurry
