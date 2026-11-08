"""Make a contact sheet of random photos from relabel/containers.csv to check the CLIP labels by eye.

  python scripts/contact_sheet.py --csv relabel/containers.csv --trashnet DIR --realwaste DIR --dataset realwaste --material plastic --decision container --out sheet.jpg
"""
import argparse
import csv
import random
from pathlib import Path

import cv2
import numpy as np

FOLDER = {"glass": "Glass", "metal": "Metal", "plastic": "Plastic"}

ap = argparse.ArgumentParser()
ap.add_argument("--csv", required=True); ap.add_argument("--trashnet", required=True); ap.add_argument("--realwaste", required=True)
ap.add_argument("--dataset", required=True); ap.add_argument("--material", required=True); ap.add_argument("--decision", required=True)
ap.add_argument("--n", type=int, default=24); ap.add_argument("--cols", type=int, default=6); ap.add_argument("--size", type=int, default=170)
ap.add_argument("--out", required=True); ap.add_argument("--seed", type=int, default=1)
a = ap.parse_args()
rows = [r for r in csv.DictReader(open(a.csv)) if r["dataset"] == a.dataset and r["material"] == a.material and r["decision"] == a.decision]
random.seed(a.seed); random.shuffle(rows)
root = Path(a.trashnet) / a.material if a.dataset == "trashnet" else Path(a.realwaste) / FOLDER[a.material]
tiles = [cv2.resize(cv2.imread(str(root / r["file"])), (a.size, a.size)) for r in rows[: a.n]]
while len(tiles) % a.cols:
    tiles.append(np.zeros((a.size, a.size, 3), np.uint8))
cv2.imwrite(a.out, np.vstack([np.hstack(tiles[i:i + a.cols]) for i in range(0, len(tiles), a.cols)]))
print(a.out, len(rows), "photos in this group")
