"""
Distance augmentation: make a close-up training photo look like the item is FAR from the camera.

Why: every public dataset photo is a close-up with the item filling the frame, but at the bin a can
held back or dropped in a tray is a small object on a messy background. A model that has only seen
close-ups calls those "waste". This shrinks the item, drops it on a different background and softens it
(lower resolution, blur, noise) the way a real distant item looks. The label never changes.

Preview what it does (writes a grid image):  python scripts/distance_aug.py [out.png]
"""
from __future__ import annotations

import math
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

IMG_EXTS = {".jpg", ".jpeg", ".png"}


def list_images(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.rglob("*") if p.suffix.lower() in IMG_EXTS and p.is_file())


def _soft_mask(size: tuple[int, int]) -> Image.Image:
    """Rounded rectangle with a feathered edge, so the pasted photo has no hard rectangular border to latch onto."""
    w, h = size
    pad = max(1, int(min(w, h) * 0.03))
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle([pad, pad, w - pad, h - pad], radius=int(min(w, h) * 0.12), fill=255)
    return m.filter(ImageFilter.GaussianBlur(max(1.0, 0.04 * min(w, h))))


def _gradient_bg(size: int, rng) -> Image.Image:
    c1 = np.array([rng.randint(20, 235) for _ in range(3)], dtype=np.float32)
    c2 = np.clip(c1 + np.array([rng.randint(-70, 70) for _ in range(3)]), 0, 255)
    ang = rng.uniform(0, math.tau)
    ys, xs = np.mgrid[0:size, 0:size].astype(np.float32) / (size - 1)
    t = np.clip((xs - 0.5) * math.cos(ang) + (ys - 0.5) * math.sin(ang) + 0.5, 0, 1)[..., None]
    arr = c1 * (1 - t) + c2 * t
    arr += np.random.default_rng(rng.randint(0, 2**31 - 1)).normal(0, rng.uniform(2, 10), arr.shape)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def _crop_resize(path: Path, size: int, rng, lo: float) -> Image.Image:
    with Image.open(path) as im:
        im = im.convert("RGB")
    w, h = im.size
    f = rng.uniform(lo, 1.0)
    cw, ch = max(8, int(w * f)), max(8, int(h * f))
    x, y = rng.randint(0, w - cw), rng.randint(0, h - ch)
    return im.crop((x, y, x + cw, y + ch)).resize((size, size), Image.BILINEAR)


def _blurred_other_bg(path: Path, size: int, rng) -> Image.Image:
    """A heavily blurred, zoomed-in crop of some OTHER training photo: realistic colours and texture, no recognisable
    objects (so it leaks no class information)."""
    return _crop_resize(path, size, rng, 0.35).filter(ImageFilter.GaussianBlur(rng.uniform(8, 22)))


def _real_bg(path: Path, size: int, rng) -> Image.Image:
    """A crop of an EMPTY frame from the bin's own camera (data/raw/backgrounds/), if the team has captured some."""
    return _crop_resize(path, size, rng, 0.4).filter(ImageFilter.GaussianBlur(rng.uniform(0, 1.5)))


def shrink_onto(img: Image.Image, bg: Image.Image, scale: float, rng, rotate: float = 0.0, aspect: float = 1.0) -> Image.Image:
    """Paste `img` onto `bg` so its longer side is `scale` x the canvas, at a random position."""
    size = bg.size[0]
    obj = img.convert("RGB")
    mask = _soft_mask(obj.size)
    if rotate:
        fill = tuple(int(v) for v in np.asarray(obj.resize((16, 16))).reshape(-1, 3).mean(0))  # not black: no dark halo
        obj = obj.rotate(rotate, expand=True, resample=Image.BILINEAR, fillcolor=fill)
        mask = mask.rotate(rotate, expand=True, resample=Image.BILINEAR)
    w, h = obj.size
    k = scale * size / max(w, h)
    nw = min(size, max(2, round(w * k * math.sqrt(aspect))))   # aspect > 1 squeezes tall, < 1 squeezes wide
    nh = min(size, max(2, round(h * k / math.sqrt(aspect))))
    obj, mask = obj.resize((nw, nh), Image.LANCZOS), mask.resize((nw, nh), Image.LANCZOS)
    out = bg.copy()
    out.paste(obj, (rng.randint(0, size - nw), rng.randint(0, size - nh)), mask)
    return out


def degrade(img: Image.Image, rng) -> Image.Image:
    """Far items are low-resolution, a little out of focus and noisy."""
    size = img.size[0]
    f = rng.uniform(0.45, 1.0)
    if f < 0.98:
        small = max(16, int(size * f))
        img = img.resize((small, small), Image.BILINEAR).resize((size, size), Image.BILINEAR)
    r = rng.uniform(0, 1.2)
    if r > 0.1:
        img = img.filter(ImageFilter.GaussianBlur(r))
    sigma = rng.uniform(0, 7)
    if sigma > 1:
        arr = np.asarray(img, dtype=np.float32)
        arr = arr + np.random.default_rng(rng.randint(0, 2**31 - 1)).normal(0, sigma, arr.shape)
        img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    return img


class DistanceAug:
    """PIL image in -> PIL image out (size x size) showing the item small, on another background, a bit degraded."""

    def __init__(self, size: int = 224, scale: tuple[float, float] = (0.12, 0.70), bg_paths=(), real_bg_paths=(),
                 max_rotate: float = 25.0):
        self.size, self.scale, self.max_rotate = size, scale, max_rotate
        self.bg_paths, self.real_bg_paths = list(bg_paths), list(real_bg_paths)

    def _background(self, rng) -> Image.Image:
        options = [("gradient", 0.25)]
        if self.bg_paths:
            options.append(("other", 0.35))
        if self.real_bg_paths:
            options.append(("real", 0.40))
        kind = rng.choices([k for k, _ in options], weights=[w for _, w in options])[0]
        if kind == "real":
            return _real_bg(rng.choice(self.real_bg_paths), self.size, rng)
        if kind == "other":
            return _blurred_other_bg(rng.choice(self.bg_paths), self.size, rng)
        return _gradient_bg(self.size, rng)

    def apply(self, img: Image.Image, rng, scale: float | None = None, degrade_p: float = 0.8) -> Image.Image:
        if scale is None:  # log-uniform: as many small items as medium ones
            scale = math.exp(rng.uniform(math.log(self.scale[0]), math.log(self.scale[1])))
        out = shrink_onto(img, self._background(rng), scale, rng,
                          rotate=rng.uniform(-self.max_rotate, self.max_rotate), aspect=math.exp(rng.uniform(-0.4, 0.4)))
        return degrade(out, rng) if rng.random() < degrade_p else out

    def __call__(self, img: Image.Image) -> Image.Image:
        return self.apply(img, random)  # the random module doubles as the rng (DataLoader seeds it per worker)


if __name__ == "__main__":
    ml_root = Path(__file__).resolve().parent.parent
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ml_root / "models" / "distance_aug_preview.png"
    pool = list_images(ml_root / "data" / "processed" / "train")
    cans = list_images(ml_root / "data" / "processed" / "train" / "cans")
    aug = DistanceAug(bg_paths=pool, real_bg_paths=list_images(ml_root / "data" / "raw" / "backgrounds"))
    rng = random.Random(7)
    cols, rows = 6, 4
    grid = Image.new("RGB", (cols * 224, rows * 224))
    for i in range(cols * rows):
        with Image.open(rng.choice(cans)) as im:
            grid.paste(aug.apply(im.convert("RGB"), rng), ((i % cols) * 224, (i // cols) * 224))
    grid.save(out)
    print(f"wrote {out}")
