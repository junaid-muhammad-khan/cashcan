# Face recognition accuracy (LFW)

Pipeline: InsightFace `buffalo_s` (ArcFace) via `app.face_engine`, the same quality gates and `match()` the bin uses. Settings: threshold 0.45, ambiguity margin 0.05, min face 80px, min detector score 0.6, min sharpness 60.0.

## 1. How often a photo is rejected before matching

Two tiers: **enrollment** (strict, because a bad frame would be saved as a template) and **identification** (lenient, because a weak frame can only fail to match). Strict: face >= 80 px, detector >= 0.6, sharpness >= 60. Lenient: face >= 48 px, detector >= 0.45, sharpness >= 25. (This run used a 60 px lenient face limit; no LFW face in this set is between 48 and 60 px, so the figures are identical with the final 48 px.)

| Reason | Pairs images, enrollment tier | Pairs images, identification tier | Identification images, enrollment tier | Identification images, identification tier |
|---|---|---|---|---|
| ok | 95.4% | 100.0% | 95.9% | 100.0% |
| no face detected | 0.0% | 0.0% | 0.0% | 0.0% |
| low detector confidence | 0.1% | 0.0% | 0.0% | 0.0% |
| face too small | 2.0% | 0.0% | 1.7% | 0.0% |
| too blurry | 2.6% | 0.0% | 2.5% | 0.0% |
| unreadable image | 0.0% | 0.0% | 0.0% | 0.0% |

Gallery (enrolled) photos must pass the enrollment tier; every photo that is only looked up needs the identification tier. Rejected photos are not counted as wrong matches below; at the bin the person is just asked to retry.

## 2. Verification: are these two photos the same person?

2199 usable pairs of 2200 (1100 same-person, 1099 different-person).

| Metric | Value |
|---|---|
| Accuracy at our threshold (0.45) | **95.04%** |
| Best possible accuracy (threshold 0.225) | 99.36% |
| ROC AUC | 0.9941 |
| Equal error rate | 1.18% (at threshold 0.16) |
| Same-person accepted at 1% false-accept | 98.82% |
| Same-person accepted at 0.1% false-accept | 98.73% |
| Mean score: same / different | 0.61 / 0.01 |

(For scale, published ArcFace-class models report about 99.5% on the official 6,000-pair LFW protocol. This uses the dataset's own pairs split, not the official 10-fold protocol, so treat the comparison as rough.)

## 3. Identification: the bin's real job

150 people enrolled with 3 photos each (0 skipped: too few usable photos). 777 later photos of those people must be recognised; 858 photos of 600 different people who are **not** enrolled must be rejected.

| Threshold | Enrolled person recognised | Wrong person named | Not recognised | Stranger accepted (95% upper bound) |
|---|---|---|---|---|
| 0.25 | 99.9% | 0.00% | 0.1% | 8.16% (70/858, <= 10.18%) |
| 0.30 | 99.9% | 0.00% | 0.1% | 2.45% (21/858, <= 3.71%) |
| 0.35 | 99.7% | 0.00% | 0.3% | 0.12% (1/858, <= 0.66%) |
| 0.40 | 99.5% | 0.00% | 0.5% | 0.12% (1/858, <= 0.66%) |
| 0.45 **(current)** | 99.0% | 0.00% | 1.0% | 0.12% (1/858, <= 0.66%) |
| 0.50 | 97.7% | 0.00% | 2.3% | 0.12% (1/858, <= 0.66%) |
| 0.55 | 93.7% | 0.00% | 6.3% | 0.12% (1/858, <= 0.66%) |
| 0.60 | 83.3% | 0.00% | 16.7% | 0.00% (0/858, <= 0.45%) |
| 0.65 | 63.6% | 0.00% | 36.4% | 0.00% (0/858, <= 0.45%) |
| 0.70 | 40.7% | 0.00% | 59.3% | 0.00% (0/858, <= 0.45%) |

With 0 strangers accepted out of N, the false-accept rate is still only bounded (about 3/N), not zero.

## 4. Is the liveness head-turn measure sane on real faces?

Compared on 4400 real faces against InsightFace's own head-yaw estimate (note: yaw sign convention may differ, only magnitude and linearity matter here).

Correlation between |turn ratio| and |yaw|: **0.93**

| |yaw| | n | median |turn ratio| | passes 'facing camera' (<= 0.12) | passes 'turned' (>= 0.25) |
|---|---|---|---|---|
| 0-5 deg | 1229 | 0.02 | 100% | 0% |
| 5-10 deg | 1002 | 0.07 | 95% | 0% |
| 10-15 deg | 805 | 0.12 | 53% | 0% |
| 15-20 deg | 664 | 0.17 | 9% | 3% |
| 20-30 deg | 535 | 0.24 | 0% | 47% |
| 30-45 deg | 132 | 0.37 | 2% | 98% |
| 45-90 deg | 33 | 0.65 | 0% | 100% |

Read: nearly all near-frontal faces should pass 'facing camera' and almost none should pass 'turned'; faces turned 30+ degrees should mostly pass 'turned'. This checks the measure, not the anti-spoof strength: LFW has no photo/screen attacks, so spoof resistance is covered only by the unit tests and the geometry argument.

## What this does and does not show

- LFW is celebrity press photos: mostly frontal, decent light, varied age. A bin webcam under venue lighting is harder. Expect worse; measure with `tools.tune` on the team.
- Gallery size is 150 people here. Accuracy drops as more people enrol.
- No spoofing is in this data, and no demographic breakdown was run: LFW is not balanced, so fairness across groups is **not** measured.
- Photos with no detectable face are excluded from accuracy and reported in section 1.


## Change log
- 2026-11-07: first run (raw-crop blur gate, one tier of gates).
- 2026-11-08: re-run with a size-independent blur measure (limit 30), still one tier.
- 2026-11-08 (latest): re-run with the two tiers of gates (strict for enrollment photos, lenient for photos that are only looked up) and a
  contrast-normalised blur measure. Identification: 99.0% recognised at 45% (was 99.2%), still 0 wrong names; the single accepted
  "stranger" is the Rosalyn Carter photo that also shows Jimmy Carter. Pair verification includes every pair now (2,199 of 2,200 instead of
  2,082), so it is slightly lower: AUC 0.9961 -> 0.9941, EER 0.96% -> 1.18%, best accuracy 99.52% -> 99.36%, because the small and soft
  photos the gates used to drop are now scored too.
