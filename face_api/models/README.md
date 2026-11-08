# Face models (InsightFace buffalo_s, ONNX)
`det_500m.onnx` (SCRFD detector, 2.4 MB) and `w600k_mbf.onnx` (MobileFaceNet/ArcFace recognizer, 13 MB), unmodified from InsightFace's buffalo_s pack.
Run by `app/lean_engine.py`, so the API deploys (e.g. on Vercel) without the insightface package. The pretrained weights are for
non-commercial research use only (see ../README.md). Override the folder with `CASHCAN_MODEL_DIR`.
