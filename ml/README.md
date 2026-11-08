# CashCan ML pipeline

Trains an image classifier that sorts an item into one of CashCan's **3 physical bins**
(organics / cans / waste), using only public datasets, then exports it for the RK3582 NPU
deployment target (Radxa ROCK 5C Lite). See `../README.md` for the overall project.

## Results (honest numbers, not cherry-picked)

Trained on TrashNet + GD (public datasets, mixed sources), tested on RealWaste - a
**third, independently-collected dataset the model never trains on**. This is a harder,
more honest test than the usual same-dataset train/test split.

| | Value |
|---|---|
| Best validation accuracy (TrashNet+GD, same distribution as training) | **97.4%** |
| **Test accuracy (RealWaste, held out)** | **72.1%** |

Per-class test results (RealWaste):

| Class | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| cans | 0.91 | 0.67 | 0.78 | 2131 |
| organics | 0.79 | 0.45 | 0.57 | 847 |
| waste | 0.60 | 0.91 | 0.72 | 1774 |

See `models/confusion_matrix.png` and `models/metrics.json` for full details.

**Why test accuracy (72%) is well below validation accuracy (97%):** this is a genuine
cross-dataset generalization gap, not a bug. RealWaste was photographed in a different
environment (landfill reception area, uniform background) than TrashNet/GD (varied web/app
sources). We tried several things to close this gap (full backbone fine-tuning instead of a
frozen head, a weighted sampler for the underrepresented organics class, heavier/randomized
augmentation) - they helped (MobileNetV3-small got 63.6%/17% organics recall before these
same fixes; MobileNetV2 with them gets 72.1%/44.5%), but a real fix requires photos from your
actual demo camera/lighting setup, which is a step for hackathon day, not something public
data alone can solve. The biggest remaining failure mode is **cans being misclassified as
waste** (653/2131 cases) - worth knowing before the demo, since it means some valid
deposit-return containers won't get the reward.

**Model choice:** MobileNetV2-1.0 (not V3, not EfficientNetV2S - both were tried and
compared) was picked because it both generalized better in our tests AND matches the
recommended garbage-classifier spec for the RK3582 NPU target (224x224 input,
INT8-quantizable, has an official Rockchip RKNN conversion example).

## Setup

```bash
cd ml
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Requires a Kaggle account + API token at `~/.kaggle/kaggle.json` to download the GD dataset
(see https://www.kaggle.com/settings/account -> API -> Create New Token).

## Reproduce everything

```bash
# 1. Download datasets into data/raw/ (RealWaste + TrashNet are public URLs; GD needs Kaggle auth)
curl -sL -o data/raw/realwaste/realwaste.zip https://archive.ics.uci.edu/static/public/908/realwaste.zip
cd data/raw/realwaste && unzip -q realwaste.zip && cd ../../..

curl -sL -o data/raw/trashnet/dataset-resized.zip \
  https://huggingface.co/datasets/garythung/trashnet/resolve/main/dataset-resized.zip
cd data/raw/trashnet && unzip -q dataset-resized.zip && rm -rf __MACOSX && cd ../../..

kaggle datasets download -d sumn2u/garbage-classification-v2 -p data/raw/gd --unzip

# 2. Build train/val/test splits per class_map.yaml (the unified 3-bin scheme)
python scripts/prepare_data.py

# 3. Train MobileNetV2 (fine-tuned, weighted sampler for class imbalance), evaluate on
#    RealWaste, export ONNX - takes ~15-20 min on Apple Silicon MPS
python scripts/train.py

# 4. Test inference on a single image
python scripts/predict.py data/processed/test/cans/some_image.jpg

# 5. (On a separate x86 Linux machine with rknn-toolkit2 installed - NOT this pipeline)
python scripts/generate_calibration_list.py   # run here first, copy calibration.txt over
python scripts/convert_rknn.py                # run on the x86 Linux machine
```

## Files

- `class_map.yaml` - maps each dataset's raw folder names onto the unified 3-bin scheme
  (organics/cans/waste), with roles (train_val vs test_only) and notes on judgment calls.
- `rules.yaml` - bin display text / reward eligibility per class. **Values are TODO** -
  do not fill these with assumed Metro Vancouver rules; verify against Recycle BC first.
- `scripts/prepare_data.py` - builds `data/processed/{train,val,test}` from the raw downloads.
- `scripts/train.py` - trains MobileNetV2, evaluates on RealWaste, exports ONNX.
- `scripts/train_efficientnet.py` - the EfficientNetV2S comparison run (not the final model).
- `scripts/predict.py` - CLI: single image in, JSON prediction out (for laptop testing).
- `scripts/generate_calibration_list.py` / `scripts/convert_rknn.py` - ONNX -> RKNN handoff
  for the RK3582 NPU deployment target (must run on x86 Linux, not this Mac).

## CREDITS

This pipeline uses three public datasets. All were downloaded as-is; no images were
collected by this team for this run.

**RealWaste** (test set only - never trained on)
Single, S., Iranmanesh, S., & Raad, R. (2023). *RealWaste* [Dataset]. UCI Machine Learning
Repository. https://doi.org/10.24432/C5SS4G
License: **CC BY 4.0** (Creative Commons Attribution 4.0 International) - attribution
required, which this section provides.

**TrashNet** (train/val)
Thung, G., & Yang, M. (2016). *trashnet* [Dataset]. https://github.com/garythung/trashnet
License: **MIT**.

**GD - The Garbage Dataset** (train/val)
Kunwar, S. (2026). *The Garbage Dataset (GD): A Multi-Class Image Benchmark for Automated
Waste Segregation*. arXiv:2602.10500. DOI: 10.5753/jbcs.2026.7774. Dataset hosted at
https://www.kaggle.com/datasets/sumn2u/garbage-classification-v2
License: **MIT** - note the arXiv paper and the original task brief both referenced
"CC BY 4.0" for this dataset, but the Kaggle page's own metadata states MIT at the time of
download (verified directly, not assumed). Citing MIT here since that's what the actual
distribution states.

All three datasets are used under their stated licenses for this non-commercial hackathon
project. If CashCan is ever commercialized, re-verify license terms (especially GD, whose
stated license differs between sources) before shipping.
