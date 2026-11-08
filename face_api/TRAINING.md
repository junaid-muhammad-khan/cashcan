# Does training an adapter on LFW help?

12809 of 13233 LFW images passed the quality gates; 5586 people, 1629 with 2+ photos (8852 images), 3957 with a single photo (used only as strangers).

Adapter: `f(e) = normalize(e + W e)`, W starts at 0 (= the pretrained model), CosFace loss on train people. Train / validation / test **people are disjoint**; early stopping and the L2 strength use validation only; if nothing beats the untrained model on validation, the adapter stays identity.

## Verification on held-out people (test pairs)

| Split | train people | test pairs | chosen L2 | epochs | Val EER base -> adapter | **Test EER base -> adapter** | 95% CI of improvement | Test TAR@1%FAR base -> adapter | Test TAR@0.1%FAR base -> adapter |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 978 | 4624 | 0 | 8 | 1.13% -> 1.13% | **1.08% -> 1.08%** | [+0.00, +0.00] pts | 98.88% -> 98.88% | 98.44% -> 98.44% |
| 1 | 978 | 4722 | 0 | 8 | 0.36% -> 0.36% | **0.55% -> 0.55%** | [+0.00, +0.00] pts | 99.45% -> 99.45% | 99.20% -> 99.20% |
| 2 | 978 | 4436 | 0 | 8 | 0.54% -> 0.54% | **0.86% -> 0.86%** | [+0.00, +0.00] pts | 99.14% -> 99.14% | 98.83% -> 98.83% |
| 3 | 978 | 4526 | 0 | 8 | 0.46% -> 0.46% | **0.40% -> 0.40%** | [+0.00, +0.00] pts | 99.60% -> 99.60% | 99.56% -> 99.56% |
| 4 | 978 | 4632 | 0 | 8 | 0.74% -> 0.74% | **0.39% -> 0.39%** | [+0.00, +0.00] pts | 99.65% -> 99.65% | 99.40% -> 99.40% |

Mean EER improvement over 5 splits: **+0.00 points** (min +0.00, max +0.00). Positive = adapter better. A CI containing 0 means the difference is not distinguishable from noise.

## Identification on held-out people (seed 0, enroll 3 photos each)

94 test people, 474 probes, 2638 stranger photos (people with one photo, never trained on).

| Threshold | Recognised base -> adapter | Wrong name base -> adapter | Strangers accepted base -> adapter |
|---|---|---|---|
| 0.30 | 99.6% -> 99.6% | 0.21% -> 0.21% | 23/2638 -> 23/2638 |
| 0.35 | 98.7% -> 98.7% | 0.21% -> 0.21% | 3/2638 -> 3/2638 |
| 0.40 | 97.9% -> 97.9% | 0.21% -> 0.21% | 1/2638 -> 1/2638 |
| 0.45 | 97.3% -> 97.3% | 0.21% -> 0.21% | 1/2638 -> 1/2638 |
| 0.50 | 95.4% -> 95.4% | 0.21% -> 0.21% | 1/2638 -> 1/2638 |
| 0.55 | 88.2% -> 88.2% | 0.21% -> 0.21% | 0/2638 -> 0/2638 |
| 0.60 | 79.3% -> 79.3% | 0.21% -> 0.21% | 0/2638 -> 0/2638 |

## Reading this

- Same train/validation/test people for both columns; the untrained model is the baseline, not a straw man.
- This measures LFW press photos only. Whatever the table shows, it says nothing certain about your bin's webcam.
- The backbone (WebFace600K) may have seen some LFW people while pretraining; I cannot rule that out, but it applies equally to both columns.


## Diagnostic: is the "no gain" a bug or real? (split 0, one run per learning rate)

Training does work: on the 978 people it trains on, the loss falls from 0.029 to ~0.000 and their equal error rate improves
from 0.40% (untrained) to 0.19-0.24%. On the 163 held-out validation people it does not improve:

| Learning rate | Train-people EER (untrained 0.40%) | Validation EER (untrained 1.13%) |
|---|---|---|
| 2e-3 | 0.19% after 1 epoch | 1.20% after 1 epoch, 1.62% at epoch 20, 1.48% at epoch 40 |
| 2e-4 | 0.24% after 40 epochs | 1.13% at every epoch |
| 2e-5 | 0.36% after 40 epochs | 1.13% at every epoch |

So the layer memorises the training identities and learns nothing that transfers to new people. The pretrained model is already
saturated for this data: with ~1,000 identities there is no generalisable signal left to add.

## Conclusion
Not adopted. No adapter is shipped and the pipeline is unchanged. Improving accuracy at the bin needs photos from the bin's own
camera and lighting (a different distribution from LFW), not more training on LFW.
