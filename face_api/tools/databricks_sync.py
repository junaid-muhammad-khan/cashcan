"""Move face templates between the local database and Databricks, and look people up in Vector Search.

  export DATABRICKS_HOST=https://dbc-38b8f0fd-7cd5.cloud.databricks.com
  export DATABRICKS_TOKEN=...            # your personal access token; never commit it
  export DATABRICKS_WAREHOUSE_ID=9a5194b5eb7321ed
  python -m tools.databricks_sync push   --name junaid        # local enrollment -> Databricks (needs consent: you enrolled it)
  python -m tools.databricks_sync pull                         # Databricks -> local database (adds people missing locally)
  python -m tools.databricks_sync search --image me.jpg        # same lookup done by Databricks Vector Search
  python -m tools.databricks_sync delete --name junaid         # removes the person from Databricks (not from the local file)
  python -m tools.databricks_sync status

Matching at the bin stays local (after `pull`). Vector Search sees new people about 2 minutes after a push.
"""
from __future__ import annotations

import argparse
import sys

import numpy as np

from app import config
from app.databricks_store import DatabricksFaces
from app.store import FaceStore


def pull_into(store: FaceStore, owners: list[str], mat: np.ndarray, wallets: dict[str, str]) -> list[str]:
    """Add every Databricks person missing from the local store. Returns the names added."""
    added = []
    for user in sorted(set(owners)):
        if store.user_exists(user):
            continue
        store.add_user(user, wallets.get(user, "UNKNOWN"), [mat[i] for i, o in enumerate(owners) if o == user])
        added.append(user)
    return added


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=config.DB_PATH)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for n in ("push", "delete"):
        sub.add_parser(n).add_argument("--name", required=True)
    s = sub.add_parser("search"); s.add_argument("--image", required=True); s.add_argument("--k", type=int, default=3)
    sub.add_parser("pull"); sub.add_parser("status")
    a = ap.parse_args(argv)

    dbx, store = DatabricksFaces(), FaceStore(a.db)
    if a.cmd == "push":
        if not store.user_exists(a.name):
            print(f"'{a.name}' is not enrolled locally. Run tools.face_demo enroll first.", file=sys.stderr); return 1
        embs = store.embeddings_for(a.name)
        print(f"pushed {dbx.push_user(a.name, store.wallet(a.name), list(embs))} templates for '{a.name}' to Databricks "
              "(Vector Search sees them in ~2 min)")
    elif a.cmd == "pull":
        owners, mat, wallets = dbx.pull_all()
        added = pull_into(store, owners, mat, wallets)
        print(f"Databricks has {len(set(owners))} people / {len(owners)} templates; added locally: {added or 'none'}")
    elif a.cmd == "delete":
        print("deleted from Databricks" if dbx.delete_user(a.name) else f"'{a.name}' not found in Databricks")
    elif a.cmd == "status":
        owners, _, _ = dbx.pull_all()
        st = dbx.index_status()
        print(f"people: {len(set(owners))}, templates: {len(owners)} | index {st.get('detailed_state')}, rows {st.get('indexed_row_count')}")
    else:  # search
        from app.face_engine import InsightFaceEngine, QualityError, check_quality, decode_image, pick_face
        from pathlib import Path

        try:
            face = pick_face(InsightFaceEngine(modules=["detection", "recognition"]).analyse(decode_image(Path(a.image).read_bytes())))
            check_quality(face)
        except QualityError as e:
            print(f"Cannot use that image: {e}", file=sys.stderr); return 1
        hits = dbx.search(face.embedding, a.k)
        for user, cos in hits:
            print(f"  {user}: cosine {cos:.3f}" + ("  (above threshold)" if cos >= config.MATCH_THRESHOLD else ""))
        if not hits:
            print("  no results (empty index?)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
