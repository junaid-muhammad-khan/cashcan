# Cans at a distance, and training on the bin's own camera

What we measured and the scripts that came out of it. Nothing here changes the model the bin uses (`models/mobilenetv2_cashcan.*`).

## The problem
The public photo sets are close-ups with the item filling the frame. At the bin a held-back can is a small object on a messy background, and the model calls it waste.
On a synthetic distance test (a held-out photo shrunk onto another background, then blurred and noised) the current model scores:

| Item fills | Accuracy | Cans recall |
|---|---|---|
| close-up | 0.92* | 0.95* |
| 50% | 0.44-0.59 | 0.27-0.69 |
| 30% | 0.39-0.47 | 0.12-0.52 |
| 20% | 0.37-0.42 | 0.03-0.42 |
| 12% | 0.38 | 0.02-0.33 |

\* from the first run. A later run printed 0.747 / 0.460 for the same cell, so the "old model" column is not trustworthy: the old model was probably left in
training mode while it was scored. Fix `old.eval()` before relying on it.

## `scripts/distance_aug.py` + `scripts/train_v2.py`
Shrinks the item to 12-70% of the frame on another background and degrades it, for ~65% of training images; warm-starts from the live model. Writes separate `*_v2.*` files.
Result of one 8-epoch run (synthetic test, so it flatters v2): cans recall at 12-50% went from ~0.02-0.27 to ~0.77-0.81 and accuracy at 12% from 0.38 to 0.56.
**Cost:** waste called cans rose (at 12%: 13 -> 434). It pays out for trash, so a cans-only confidence threshold is needed before using it. The weights were deleted and are not in git.

## `scripts/train_camera.py`
Fine-tunes on photos taught at the bin (`~/.cashcan/taught_photos/<bin>/`, made with the R/O/W keys), mixed with the public set. Holds out whole "holds" (frames <3 s apart) for testing.
The first session had 403 photos from only 10 holds (cans 6, waste 3, organics 1), all from one room: a weak test. Collect more varied holds (different distances, angles, lighting) before trusting it.

## Known gaps
- The ROI (about 70% x 60% of the frame) was squashed into a square at inference, so cans looked tall and thin. Main now crops tightly around the item instead.
- `pi_client/requirements.txt` does not list `onnx`, which `TeachableClassifier` needs.
- The bin defaults to the INT8 model; any new model needs `scripts/quantize_int8.py` before it can replace it.
