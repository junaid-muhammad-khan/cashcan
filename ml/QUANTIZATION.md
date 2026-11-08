# Smaller, faster models for the bin: what was measured

Measured on a 4-core x86 cloud machine with ONNX Runtime, **not on a Raspberry Pi or the Radxa NPU**. Sizes and accuracy carry over; absolute
speeds on the real board will differ (INT8 usually helps more on ARM CPUs, but that is not verified here). Reproduce with the two tools named below.

## Where the time actually went
| Stage | Time |
|---|---|
| Face detect + align + embed, one face (the on-bin pipeline) | ~17-20 ms |
| Object classifier (MobileNetV2, FP32), one item | ~7 ms with preprocessing |
| One identification through the face server (network, Databricks, cold starts) | 0.5 to 4 s, measured on the live site |

The models were never the slow part. **Identifying on the device removes the network from every frame** (`--local-identity`, `pi_client/cashcan_pi/local.py`):
a full identification of a 640x480 JPEG, including decoding, detection, embedding and matching, takes **~17 ms (median)**.

## Object classifier: INT8 (`scripts/quantize_int8.py`)
Static INT8 quantization (QDQ, per-channel), calibrated on 400 unlabeled photos mixed from TrashNet and RealWaste (the real-world, damaged items matter).
Evaluated on 1,500 photos from both datasets (100 per material folder), FP32 vs INT8 on the same photos:

| | Size | Latency | Accuracy | Cans | Organics | Waste |
|---|---|---|---|---|---|---|
| FP32 | 8.9 MB | 2.1 ms | 96.7% | 99.0% | 99.0% | 94.1% |
| **INT8** | **2.6 MB** | **1.4 ms** | **96.3%** | 98.2% | 99.0% | 94.0% |

The two models give the same bin on 98.9% of photos. **Cost: 0.4 points of accuracy for a 3.4x smaller file and ~1.5x faster.** The INT8 file is the default in
`pi_client`; pass `--model ml/models/mobilenetv2_cashcan.onnx` for FP32. Caveat: about 60% of RealWaste and all of TrashNet were in training, so these
percentages are a comparison between the two models, not a held-out score (the 94.1% held-out figure in README.md still stands for FP32). For the RK3582 NPU the
RKNN conversion (`convert_rknn.py`) does its own INT8 quantization.

## Face recognizer: INT8 tried, NOT adopted (`face_api/tools/quantize_face.py`)
Calibrated on 300 aligned face crops, evaluated on 2,200 LFW verification pairs:

| | Size | Latency | Best-threshold accuracy | True accepts at 0.1% false accepts |
|---|---|---|---|---|
| FP32 | 13.6 MB | 6.4 ms | 94.0% | 88.1% |
| INT8 | 3.7 MB | 14.7 ms | 94.0% | 88.1% |

Verification quality held, but on this CPU INT8 was **slower** (14.7 vs 6.4 ms), and the INT8 embeddings differ from the FP32 ones (mean cosine 0.957, worst 0.66 for the same
photo). Every enrolled template was made with the FP32 model, so matching INT8 queries against them would lower scores, and re-enrolling everyone is not worth saving 10 MB.
The face models stay FP32 (2.5 MB detector + 13.6 MB recognizer). Worth re-testing on the real board.
