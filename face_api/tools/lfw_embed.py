"""Embed every LFW image once (resumable), for training/evaluating things on top of the frozen model.

  python -m tools.lfw_embed --data DIR --out DIR/emb      # DIR has data.parquet (huggingface.co/datasets/logasja/lfw)

Writes chunk_0000.npz ... with label, md5 of the image bytes (to match other splits), status code
(see tools.eval_lfw.REASONS) and the 512-d embedding. Re-running skips finished chunks.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import time
from pathlib import Path

import numpy as np

from tools.eval_lfw import classify


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--chunk", type=int, default=1000)
    a = ap.parse_args(argv)
    import pyarrow.parquet as pq

    from app.face_engine import InsightFaceEngine

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    engine = InsightFaceEngine(modules=["detection", "recognition"])
    rows_seen, t0, done = 0, time.time(), 0
    buf: list[tuple[int, bytes]] = []

    def flush(idx: int, items: list[tuple[int, bytes]]):
        path = out / f"chunk_{idx:04d}.npz"
        if path.exists():
            return
        n = len(items)
        label, md5 = np.zeros(n, np.int32), np.empty(n, "U32")
        st, emb = np.zeros(n, np.int8), np.zeros((n, 512), np.float32)
        for i, (lab, b) in enumerate(items):
            label[i], md5[i] = lab, hashlib.md5(b).hexdigest()
            s, e, _, _ = classify(engine, b)
            st[i] = s
            if e is not None:
                emb[i] = e
        np.savez_compressed(path, label=label, md5=md5, status=st, emb=emb)

    chunk_idx = 0
    pf = pq.ParquetFile(Path(a.data) / "data.parquet")
    total = pf.metadata.num_rows
    for batch in pf.iter_batches(batch_size=256, columns=["label", "image"]):
        for lab, img in zip(batch.column("label").to_pylist(), batch.column("image").to_pylist()):
            buf.append((lab, img["bytes"]))
            if len(buf) == a.chunk:
                existed = (out / f"chunk_{chunk_idx:04d}.npz").exists()
                flush(chunk_idx, buf)
                chunk_idx, buf = chunk_idx + 1, []
                done += 0 if existed else a.chunk
                rate = done / max(time.time() - t0, 1e-9)
                print(f"  chunk {chunk_idx} ({chunk_idx * a.chunk}/{total}) {rate:.1f} img/s", file=sys.stderr, flush=True)
    if buf:
        flush(chunk_idx, buf)
    print("embedding finished", file=sys.stderr, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
