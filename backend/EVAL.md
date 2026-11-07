# Face recognition accuracy (LFW)

Pipeline: InsightFace `buffalo_s` (ArcFace) via `app.face_engine`, the same quality gates and `match()` the bin uses. Settings: threshold 0.45, ambiguity margin 0.05, min face 80px, min detector score 0.6, min sharpness 40.0.

## 1. How often a photo is rejected before matching

| Gate | Pairs images | Identification images |
|---|---|---|
| ok | 96.8% | 97.3% |
| no face detected | 0.0% | 0.0% |
| low detector confidence | 0.1% | 0.0% |
| face too small | 2.0% | 1.7% |
| too blurry | 1.2% | 1.0% |
| unreadable image | 0.0% | 0.0% |

Rejected photos are not counted as wrong matches below. At the bin the person is just asked to retry.

## 2. Verification: are these two photos the same person?

2057 usable pairs of 2200 (1031 same-person, 1026 different-person).

| Metric | Value |
|---|---|
| Accuracy at our threshold (0.45) | **95.33%** |
| Best possible accuracy (threshold 0.225) | 99.56% |
| ROC AUC | 0.9970 |
| Equal error rate | 0.88% (at threshold 0.17) |
| Same-person accepted at 1% false-accept | 99.22% |
| Same-person accepted at 0.1% false-accept | 99.13% |
| Mean score: same / different | 0.61 / 0.01 |

(For scale, published ArcFace-class models report about 99.5% on the official 6,000-pair LFW protocol. This uses the dataset's own pairs split, not the official 10-fold protocol, so treat the comparison as rough.)

## 3. Identification: the bin's real job

150 people enrolled with 3 photos each (0 skipped: too few usable photos). 757 later photos of those people must be recognised; 831 photos of 600 different people who are **not** enrolled must be rejected.

| Threshold | Enrolled person recognised | Wrong person named | Not recognised | Stranger accepted (95% upper bound) |
|---|---|---|---|---|
| 0.25 | 99.9% | 0.00% | 0.1% | 8.30% (69/831, <= 10.38%) |
| 0.30 | 99.9% | 0.00% | 0.1% | 2.41% (20/831, <= 3.69%) |
| 0.35 | 99.7% | 0.00% | 0.3% | 0.12% (1/831, <= 0.68%) |
| 0.40 | 99.6% | 0.00% | 0.4% | 0.12% (1/831, <= 0.68%) |
| 0.45 **(current)** | 99.2% | 0.00% | 0.8% | 0.12% (1/831, <= 0.68%) |
| 0.50 | 97.9% | 0.00% | 2.1% | 0.12% (1/831, <= 0.68%) |
| 0.55 | 93.7% | 0.00% | 6.3% | 0.12% (1/831, <= 0.68%) |
| 0.60 | 83.6% | 0.00% | 16.4% | 0.00% (0/831, <= 0.46%) |
| 0.65 | 64.6% | 0.00% | 35.4% | 0.00% (0/831, <= 0.46%) |
| 0.70 | 41.6% | 0.00% | 58.4% | 0.00% (0/831, <= 0.46%) |

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

