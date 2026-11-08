"""Move face templates between the local database and Databricks, and look people up in Vector Search.

  export DATABRICKS_HOST=https://dbc-38b8f0fd-7cd5.cloud.databricks.com
  export DATABRICKS_TOKEN=...            # your personal access token; never commit it
  export DATABRICKS_WAREHOUSE_ID=9a5194b5eb7321ed
  python -m tools.databricks_sync push   --name junaid        # local enrollment -> Databricks (needs consent: you enrolled it)
  python -m tools.databricks_sync push   --name junaid --replace   # same person already there: replace with the local templates
  python -m tools.databricks_sync pull                         # Databricks -> local database (adds people missing locally)
  python -m tools.databricks_sync search --webcam              # take a photo from the camera, ask Databricks Vector Search who it is
  python -m tools.databricks_sync search --image me.jpg        # same, from a JPG or PNG file
  python -m tools.databricks_sync delete --name junaid         # removes the person from Databricks (not from the local file)
  python -m tools.databricks_sync status

Matching at the bin stays local (after `pull`). Vector Search sees new people about 2 minutes after a push.
"""
from __future__ import annotations

import argparse
import sys

import numpy as np

from app import config
from app.databricks_store import DatabricksError, DatabricksFaces
from app.store import FaceStore
from tools.face_demo import PLACEHOLDER_WALLET


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
    p = sub.add_parser("push"); p.add_argument("--name", required=True)
    p.add_argument("--replace", action="store_true", help="the person already exists in Databricks: replace their templates with the local ones")
    sub.add_parser("delete").add_argument("--name", required=True)
    s = sub.add_parser("search"); s.add_argument("--image"); s.add_argument("--webcam", action="store_true")
    s.add_argument("--camera", default="0"); s.add_argument("--k", type=int, default=3)
    sub.add_parser("pull"); sub.add_parser("status")
    a = ap.parse_args(argv)

    try:
        dbx = DatabricksFaces()
    except DatabricksError as e:
        print(f"{e}\nSet them in THIS terminal first (a new terminal window forgets them):\n"
              "  export DATABRICKS_HOST=https://<your-workspace>.cloud.databricks.com\n"
              "  export DATABRICKS_WAREHOUSE_ID=<your-warehouse-id>\n"
              "  read -s DATABRICKS_TOKEN && export DATABRICKS_TOKEN     # paste the token; it is not shown or saved", file=sys.stderr)
        return 2
    store = FaceStore(a.db)
    dbx.notify = lambda m: print(m, flush=True)
    try:
        return run(a, dbx, store)
    except KeyboardInterrupt:
        if dbx.writes_done:
            print("\nInterrupted while waiting for the search index. Your templates ARE saved in Databricks; the index catches up on its "
                  "own (check with `status`).")
        else:
            print("\nInterrupted before finishing. Run `status` to see what is in Databricks, then repeat the command (use --replace to overwrite).")
        return 130


def run(a, dbx, store) -> int:
    if a.cmd == "push":
        if not store.user_exists(a.name):
            print(f"'{a.name}' is not enrolled locally. Run tools.face_demo enroll first.", file=sys.stderr); return 1
        embs = store.embeddings_for(a.name)
        wallet = store.wallet(a.name)
        if a.replace and dbx.user_exists(a.name):
            remote = dbx.get_wallet(a.name)
            if remote and wallet == PLACEHOLDER_WALLET:
                wallet = remote  # never overwrite a real wallet in Databricks with the local placeholder
            dbx.delete_user(a.name, sync=False)  # push_user refreshes the index once, afterwards
            print(f"replaced the existing '{a.name}' in Databricks")
        print(f"pushed {dbx.push_user(a.name, wallet, list(embs))} templates for '{a.name}' to Databricks "
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
        import time
        from pathlib import Path

        from app.face_engine import InsightFaceEngine, QualityError, decode_image
        from tools.face_demo import face_from_camera, largest_usable, pct

        if not a.webcam and not a.image:
            print("Say what to look up: --webcam (takes a photo from your camera) or --image <path to a JPG or PNG>.", file=sys.stderr)
            return 2
        if a.image and not a.webcam:
            image = Path(a.image).expanduser()
            if not image.is_file():
                print(f"Cannot find an image at '{image}'. Give the path of a real JPG or PNG photo of a face "
                      "(tip: drag the file into this window to paste its path), or use --webcam.", file=sys.stderr)
                return 1
        engine = InsightFaceEngine(modules=["detection", "recognition"])
        try:
            if a.webcam:
                print("Look at the camera: taking a photo...", flush=True)
                face = face_from_camera(engine, a.camera)
            else:
                face = largest_usable(engine, decode_image(image.read_bytes()), identification=True)
        except QualityError as e:
            print(f"Cannot use that photo: {e}", file=sys.stderr)
            return 1
        t0 = time.time()
        hits = dbx.search(face.embedding, a.k)
        print(f"Databricks Vector Search answered in {(time.time() - t0) * 1000:.0f} ms. Closest people to this face:")
        for user, cos in hits:
            print(f"  {user}: {pct(cos)} similar" + (f"   <- above the {pct(config.MATCH_THRESHOLD)} match line" if cos >= config.MATCH_THRESHOLD else ""))
        if not hits:
            print("  no results (is the index empty?)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
