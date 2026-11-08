"""
Convert the trained MobileNetV2 ONNX model to RKNN format for the RK3582 NPU
(Radxa ROCK 5C Lite). This is the garbage-classification model only - the face
detection/recognition models from the deployment plan are a separate workstream.

IMPORTANT: this does NOT run on this Mac. RKNN-Toolkit2 only supports x86 Linux
(Ubuntu 18.04/20.04 per Rockchip's docs). Run this script on an x86 Linux dev
machine with `pip install rknn-toolkit2` after copying over:
  - models/mobilenetv2_cashcan.onnx  (produced by train.py)
  - models/calibration.txt            (produced by generate_calibration_list.py)

Usage (on x86 Linux): python convert_rknn.py
"""
from pathlib import Path

ML_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ML_ROOT / "models"

# Standard ImageNet normalization, expressed in RKNN's 0-255 pixel-domain convention
# (RKNN applies (pixel - mean_values) / std_values directly to 0-255 input, rather than
# the 0-1 range torchvision normalizes in). These values MUST match train.py's
# transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]):
#   mean_values = [m * 255 for m in (0.485, 0.456, 0.406)]
#   std_values  = [s * 255 for s in (0.229, 0.224, 0.225)]
# Do not change these to match a different example without re-deriving from train.py.
MEAN_VALUES = [[123.675, 116.28, 103.53]]
STD_VALUES = [[58.395, 57.12, 57.375]]


def main():
    from rknn.api import RKNN  # only importable on x86 Linux with rknn-toolkit2 installed

    onnx_path = MODELS_DIR / "mobilenetv2_cashcan.onnx"
    calibration_path = MODELS_DIR / "calibration.txt"
    rknn_path = MODELS_DIR / "mobilenetv2_cashcan.rknn"

    if not onnx_path.exists():
        raise FileNotFoundError(f"{onnx_path} not found - run train.py first")
    if not calibration_path.exists():
        raise FileNotFoundError(f"{calibration_path} not found - run generate_calibration_list.py first")

    rknn = RKNN(verbose=True)
    rknn.config(
        target_platform="rk3588",  # RK3582's RKNN conversion target is rk3588 per Radxa docs
        mean_values=MEAN_VALUES,
        std_values=STD_VALUES,
    )

    print(f"Loading ONNX model from {onnx_path}")
    ret = rknn.load_onnx(model=str(onnx_path))
    if ret != 0:
        raise RuntimeError("load_onnx failed")

    print("Building with INT8 quantization...")
    ret = rknn.build(do_quantization=True, dataset=str(calibration_path))
    if ret != 0:
        raise RuntimeError("build failed")

    print(f"Exporting RKNN model to {rknn_path}")
    ret = rknn.export_rknn(str(rknn_path))
    if ret != 0:
        raise RuntimeError("export_rknn failed")

    rknn.release()
    print(f"Done. Copy {rknn_path} to the ROCK 5C Lite and load with RKNN-Toolkit-Lite2 / RKNPU2.")


if __name__ == "__main__":
    main()
