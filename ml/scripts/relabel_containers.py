"""Relabel the material photos (glass / metal / plastic) by WHAT THE ITEM IS: a recyclable container or not.

The datasets are labelled by material, so "plastic" is mostly trays, bags, wrappers and lids, and "metal" includes foil, chip bags and spray cans.
CashCan's rule is: Recycle ("cans" bin) = cans and bottles that can be recycled; Organics = food; Waste = everything else.
This script uses CLIP (zero-shot, openai/clip-vit-base-patch32) to give every glass/metal/plastic photo a container probability, and writes
relabel/containers.csv. Photos CLIP is not sure about are marked 'unsure' and are left OUT of training rather than guessed.
Always spot-check the result by eye (scripts/contact_sheet.py) before trusting it.

  python scripts/relabel_containers.py --trashnet DIR --realwaste DIR
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import torch
from PIL import Image
from transformers import CLIPModel, CLIPProcessor

CONTAINER = [
    "a photo of a drink can", "a photo of a soda can", "a photo of a metal food tin can", "a photo of an aerosol spray can",
    "a photo of a plastic water bottle", "a photo of a plastic drink bottle", "a photo of a glass bottle", "a photo of a glass jar",
    "a photo of a juice box or drink carton", "a photo of a milk jug",
]
OTHER = [
    "a photo of a plastic food tray", "a photo of a plastic bag", "a photo of a snack wrapper or chip bag", "a photo of crumpled aluminum foil",
    "a photo of a plastic lid or bottle cap", "a photo of broken glass", "a photo of a plastic cup", "a photo of styrofoam packaging",
    "a photo of a piece of trash", "a photo of a flower pot", "a photo of a plastic container lid", "a photo of cling film or plastic wrap",
    "a photo of a toothbrush or small plastic item", "a photo of a cardboard box",
]
EXT = {".jpg", ".jpeg", ".png"}


def feats(out):
    """Newer transformers versions return an output object whose pooler_output holds the projected features."""
    return out if isinstance(out, torch.Tensor) else out.pooler_output


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trashnet", required=True)
    ap.add_argument("--realwaste", required=True)
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "relabel" / "containers.csv"))
    ap.add_argument("--sure", type=float, default=0.70, help="container probability >= this -> container; <= 1-this -> other; between -> unsure")
    a = ap.parse_args()

    model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").eval()
    proc = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
    prompts = CONTAINER + OTHER
    with torch.no_grad():
        t = feats(model.get_text_features(**proc(text=prompts, return_tensors="pt", padding=True)))
        t = t / t.norm(dim=-1, keepdim=True)
    n_c = len(CONTAINER)

    jobs = []   # (dataset, material, path)
    for m in ("glass", "metal", "plastic"):
        jobs += [("trashnet", m, p) for p in sorted((Path(a.trashnet) / m).iterdir()) if p.suffix.lower() in EXT]
    for m, folder in (("glass", "Glass"), ("metal", "Metal"), ("plastic", "Plastic")):
        jobs += [("realwaste", m, p) for p in sorted((Path(a.realwaste) / folder).iterdir()) if p.suffix.lower() in EXT]
    print(len(jobs), "photos to label", flush=True)

    rows = []
    B = 32
    for i in range(0, len(jobs), B):
        batch = jobs[i:i + B]
        imgs = [Image.open(p).convert("RGB") for _, _, p in batch]
        with torch.no_grad():
            f = feats(model.get_image_features(**proc(images=imgs, return_tensors="pt")))
            f = f / f.norm(dim=-1, keepdim=True)
            probs = (100.0 * f @ t.T).softmax(-1)
        for (ds, mat, p), pr in zip(batch, probs):
            pc = float(pr[:n_c].sum())
            rows.append((ds, mat, p.relative_to(Path(a.trashnet if ds == "trashnet" else a.realwaste).parent).as_posix() if False else p.name, f"{pc:.3f}",
                         "container" if pc >= a.sure else "other" if pc <= 1 - a.sure else "unsure"))
        if (i // B) % 10 == 0:
            print(f"  {i + len(batch)}/{len(jobs)}", flush=True)
    Path(a.out).parent.mkdir(exist_ok=True)
    with open(a.out, "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["dataset", "material", "file", "container_prob", "decision"]); w.writerows(rows)
    from collections import Counter
    for ds in ("trashnet", "realwaste"):
        for m in ("glass", "metal", "plastic"):
            c = Counter(r[4] for r in rows if r[0] == ds and r[1] == m)
            print(f"{ds:10}{m:8} container {c['container']:4}  other {c['other']:4}  unsure {c['unsure']:4}")


if __name__ == "__main__":
    main()
