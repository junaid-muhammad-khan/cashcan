"""End-to-end check of the Databricks face database with 100 photos of 100 different people (LFW).

  export DATABRICKS_HOST=... DATABRICKS_TOKEN=... DATABRICKS_WAREHOUSE_ID=...
  python -m tools.databricks_check --data DIR --report DATABRICKS_CHECK.md      # DIR has data.parquet (see tools.eval_lfw)

What it does: enrols N people (3 templates each) in Databricks under the id prefix `lfwtest-`, waits for the Vector Search
index to catch up, then runs 100 photos (N enrolled people's held-out photo + strangers) through the real pipeline and
looks each one up two ways: locally on the templates pulled back from Databricks, and with Databricks Vector Search,
using the same threshold and ambiguity rule. It reports accuracy, whether the two lookups agree, and latency, and it
ALWAYS deletes its test people afterwards (these are public-benchmark photos of real people, not to be kept).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

from app import config
from app.databricks_store import DatabricksFaces
from app.face_engine import InsightFaceEngine, QualityError, check_quality, decode_image, pick_face
from app.matching import match

PREFIX = "lfwtest-"


def embed(engine, data: bytes):
    try:
        f = pick_face(engine.analyse(decode_image(data)))
        check_quality(f)
        return f.embedding
    except QualityError:
        return None


def vs_decision(hits: list[tuple[str, float]], threshold: float, margin: float):
    """Same rule as app.matching.match, applied to Vector Search's best-cosine-per-user list."""
    if not hits:
        return None, "no_results"
    (u, c), rest = hits[0], hits[1:]
    if c < threshold:
        return None, "below_threshold"
    if rest and c - rest[0][1] < margin:
        return None, "ambiguous"
    return u, "ok"


def pick_people(path, n_enrolled, n_strangers, seed, engine):
    import pyarrow.parquet as pq

    pf = pq.ParquetFile(path)
    names = json.loads(pf.schema_arrow.metadata[b"huggingface"])["info"]["features"]["label"]["names"]
    labels = np.array(pq.read_table(path, columns=["label"]).column("label").to_pylist())
    rng = np.random.default_rng(seed)
    uniq, counts = np.unique(labels, return_counts=True)
    order = rng.permutation(uniq)
    want_enrol = [int(p) for p in order if counts[uniq == p][0] >= 4]
    want_other = [int(p) for p in order]
    # read all images of the candidate people once
    cand = set(want_enrol[: n_enrolled * 3]) | set(want_other[: (n_enrolled + n_strangers) * 4])
    blobs: dict[int, list[bytes]] = {}
    seen = 0
    for batch in pf.iter_batches(batch_size=512, columns=["label", "image"]):
        for lab, img in zip(batch.column("label").to_pylist(), batch.column("image").to_pylist()):
            if lab in cand:
                blobs.setdefault(lab, []).append(img["bytes"])
    enrolled, probes, skipped = {}, [], 0
    for p in want_enrol:
        if len(enrolled) == n_enrolled:
            break
        embs = [e for e in (embed(engine, b) for b in blobs.get(p, [])) if e is not None]
        if len(embs) < 4:
            skipped += 1
            continue
        enrolled[p] = embs[:3]
        probes.append((p, "enrolled", embs[3]))
    strangers = 0
    for p in want_other:
        if strangers == n_strangers:
            break
        if p in enrolled or p not in blobs:
            continue
        e = next((x for x in (embed(engine, b) for b in blobs[p]) if x is not None), None)
        if e is None:
            skipped += 1
            continue
        probes.append((p, "stranger", e))
        strangers += 1
    return names, enrolled, probes, skipped


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True)
    ap.add_argument("--report", default="DATABRICKS_CHECK.md")
    ap.add_argument("--enrolled", type=int, default=30)
    ap.add_argument("--strangers", type=int, default=70)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)
    db = DatabricksFaces()
    leftovers = [r[0] for r in db.sql(f"SELECT user_id FROM {db.schema}.users WHERE user_id LIKE '{PREFIX}%'")]
    if leftovers:
        print(f"{len(leftovers)} leftover test people from an earlier run: deleting first", file=sys.stderr)
        db.delete_many(leftovers)

    engine = InsightFaceEngine(modules=["detection", "recognition"])
    names, enrolled, probes, skipped = pick_people(Path(a.data) / "data.parquet", a.enrolled, a.strangers, a.seed, engine)
    ids = {p: f"{PREFIX}{p}" for p in enrolled}
    out, w = [], None
    w = out.append
    created = False
    try:
        t0 = time.time()
        n_users, n_tpl = db.push_many({ids[p]: ("TEST-NO-WALLET", e) for p, e in enrolled.items()})
        created = True
        t_push = time.time() - t0
        print(f"pushed {n_users} people / {n_tpl} templates in {t_push:.0f}s; waiting for Vector Search...", file=sys.stderr, flush=True)
        t0, indexed = time.time(), None
        for _ in range(60):
            st = db.index_status()
            if st.get("detailed_state") == "ONLINE_NO_PENDING_UPDATE" and st.get("indexed_row_count") == n_tpl:
                indexed = time.time() - t0
                break
            time.sleep(10)
        t0 = time.time()
        owners, mat, _ = db.pull_all()
        t_pull = time.time() - t0
        mine = [i for i, o in enumerate(owners) if o.startswith(PREFIX)]
        assert len(mine) == n_tpl, f"pulled {len(mine)} test templates, expected {n_tpl}"

        rows, lat = [], []
        for p, kind, emb in probes:
            loc = match(emb, owners, mat, threshold=config.MATCH_THRESHOLD, margin=config.AMBIGUITY_MARGIN)
            t0 = time.time()
            hits = db.search(emb, k=3)
            lat.append(time.time() - t0)
            vs_user, vs_reason = vs_decision(hits, config.MATCH_THRESHOLD, config.AMBIGUITY_MARGIN)
            rows.append(dict(person=names[p], kind=kind, expect=ids.get(p), local=loc.user_id, local_reason=loc.reason,
                             local_score=loc.score, vs=vs_user, vs_reason=vs_reason, vs_cos=hits[0][1] if hits else None))
        enr = [r for r in rows if r["kind"] == "enrolled"]
        stg = [r for r in rows if r["kind"] == "stranger"]
        agree = sum(r["local"] == r["vs"] for r in rows)
        w("# Databricks database check (100 photos of 100 different people)\n")
        w(f"Pipeline: real face model -> quality gates -> match with threshold {config.MATCH_THRESHOLD}, margin {config.AMBIGUITY_MARGIN}. "
          f"{n_users} people ({n_tpl} templates) enrolled in `workspace.cashcan_faces`; {len(probes)} probe photos "
          f"({len(enr)} are a different photo of an enrolled person, {len(stg)} are people who are not enrolled). "
          f"{skipped} candidate people were skipped because their photos failed the quality gates.\n")
        w("| Check | Local matching (templates pulled from Databricks) | Databricks Vector Search |\n|---|---|---|")
        for label, key in (("local", "local"), ("vs", "vs")):
            pass
        ok_l = sum(r["local"] == r["expect"] for r in enr); ok_v = sum(r["vs"] == r["expect"] for r in enr)
        wr_l = sum(r["local"] not in (None, r["expect"]) for r in enr); wr_v = sum(r["vs"] not in (None, r["expect"]) for r in enr)
        fa_l = sum(r["local"] is not None for r in stg); fa_v = sum(r["vs"] is not None for r in stg)
        w(f"| Enrolled person recognised | {ok_l}/{len(enr)} | {ok_v}/{len(enr)} |")
        w(f"| Enrolled person given the wrong name | {wr_l}/{len(enr)} | {wr_v}/{len(enr)} |")
        w(f"| Stranger accepted | {fa_l}/{len(stg)} | {fa_v}/{len(stg)} |")
        w(f"\n**The two lookups agree on {agree}/{len(rows)} photos.**\n")
        bad = [r for r in rows if (r["kind"] == "enrolled" and r["local"] != r["expect"]) or (r["kind"] == "stranger" and r["local"])
               or r["local"] != r["vs"]]
        if bad:
            w("Photos that were not handled perfectly:\n")
            for r in bad:
                w(f"- {r['person']} ({r['kind']}): local -> {r['local']} ({r['local_reason']}, {r['local_score']:.2f}); "
                  f"Vector Search -> {r['vs']} ({r['vs_reason']}, cosine {r['vs_cos'] if r['vs_cos'] is None else round(r['vs_cos'], 2)})")
        w("\n| Timing | Value |\n|---|---|")
        w(f"| Push {n_users} people / {n_tpl} templates (bulk) | {t_push:.0f}s |")
        w(f"| Vector Search caught up after the push | {('%.0fs' % indexed) if indexed else 'did not within 10 min'} |")
        w(f"| Pull all templates from Delta | {t_pull:.1f}s |")
        w(f"| Vector Search query, mean / 95th percentile | {np.mean(lat) * 1000:.0f} ms / {np.percentile(lat, 95) * 1000:.0f} ms |")
        w("\n(Public-benchmark photos of real people; test rows were deleted afterwards. LFW is easier than a bin webcam.)")
    finally:
        if created:
            n = db.delete_many(list(ids.values()))
            left = db.sql(f"SELECT count(*) FROM {db.schema}.users WHERE user_id LIKE '{PREFIX}%'")[0][0]
            tpl = db.sql(f"SELECT count(*) FROM {db.schema}.face_templates WHERE user_id LIKE '{PREFIX}%'")[0][0]
            print(f"cleanup: deleted {n} test people; remaining test rows: users={left}, templates={tpl}", file=sys.stderr, flush=True)
            if out:
                out.append(f"\nCleanup: {n} test people deleted; remaining test rows in the database: users={left}, templates={tpl}.")
    Path(a.report).write_text("\n".join(out) + "\n")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
